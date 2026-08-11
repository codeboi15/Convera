# System Design Notes

Answers to the questions this architecture invites: why these datastores, how
far they go, and when the service boundaries should move.

- [1. Why Redis](#1-why-redis)
- [2. Scaling Redis](#2-scaling-redis)
- [3. Why Postgres and not a NoSQL database](#3-why-postgres-and-not-a-nosql-database)
- [4. Where NoSQL would genuinely be better](#4-where-nosql-would-genuinely-be-better)
- [5. Service-based architecture](#5-service-based-architecture)
- [6. Horizontal scaling and load balancing](#6-horizontal-scaling-and-load-balancing)

---

## 1. Why Redis

Redis does **three** jobs here, and the fact that it is one component doing
three jobs is most of the justification.

| Job | Why Redis specifically |
| --- | --- |
| **Socket.IO pub/sub** | Required for multi-instance realtime. Without a shared backplane, a message published on API instance A never reaches a socket held by instance B — adding a second replica silently breaks delivery for half your users. `python-socketio` ships a Redis manager; this is the standard answer. |
| **Job queue** (`arq`) | Sub-millisecond enqueue, atomic pop, native delayed/scheduled jobs. |
| **Rate-limit counters** | `INCR` + `EXPIRE` is atomic and O(1); counters must be shared across replicas or the limit multiplies by replica count. |
| **Presence** | Keys with a TTL, refreshed by heartbeat. A crashed instance's users expire on their own — no cleanup job, no ghost "online" agents. |

The presence case is the clearest illustration of *why Redis rather than
Postgres*: presence is high-write, low-value, and self-expiring. Writing a row
per heartbeat every 25 seconds per connected user, then sweeping stale rows,
would be pure waste in a database whose durability guarantees you are paying
for and do not want here. Redis TTLs express "this fact is true for 25 seconds"
natively.

**The alternative considered:** Postgres `LISTEN/NOTIFY` for fan-out plus a
Postgres-backed queue, dropping Redis entirely. That is genuinely appealing —
one datastore, transactional enqueue, no lost jobs. It was rejected because
`LISTEN/NOTIFY` payloads are capped at 8 KB, notifications are dropped rather
than queued if a listener is slow, and every connected listener holds a
database connection — which collides with the connection ceiling that is
already this system's tightest constraint.

---

## 2. Scaling Redis

### How far it goes as-is

A single Redis node handles tens of thousands of operations per second. This
system's Redis traffic is bounded by *email volume and connected agents*, not
by end-user chat volume — chat messages go to Postgres and fan out through
pub/sub, but that is one publish per message. Realistically a single node
covers this product to a scale far past where Postgres becomes the problem.

### The real limits, in the order they bite

1. **Memory.** The queue lives in RAM. A long backlog risks eviction, which
   means silently dropped jobs. Mitigation: alert on queue depth, set
   `maxmemory-policy noeviction` so Redis refuses writes rather than discarding
   them.
2. **Durability.** Persistence is periodic (RDB snapshots / AOF with fsync
   intervals), so a crash can lose recently enqueued jobs. This is acceptable
   here because the *message* is already durable in Postgres — only the
   instruction to send it is lost, and it can be re-enqueued.
3. **Single-threaded command execution.** One core executes commands. A slow
   command (`KEYS`, a large `SORT`) blocks everything.
4. **No consumer groups in `arq`.** Redis Streams support them; `arq` uses
   lists, so there is one logical queue with no partitioning and no independent
   replay.

### The scaling ladder

| Stage | Action | Buys you |
| --- | --- | --- |
| 1 | Add worker replicas against one Redis | Throughput. Nothing else changes — `arq`'s `cron(unique=True)` keeps scheduled jobs from double-firing |
| 2 | Redis replica + automatic failover (Sentinel, or the platform's managed HA) | Availability |
| 3 | Separate Redis instances per role — queue, pub/sub, rate limits | Isolation: a queue backlog stops evicting rate-limit counters, and each can be sized for its own access pattern |
| 4 | Redis Cluster, sharded by key | Memory and throughput past one node |
| 5 | Move the *queue* off Redis | Durability and replay — see below |

Stage 3 is the highest-value step and the one most people skip. These three
workloads have nothing in common: pub/sub is fire-and-forget, the queue is
backlog-prone, rate limits are tiny and hot. Sharing one instance means the
queue's memory pressure can evict the limiter's counters.

### When to leave Redis

- **Durability or audit requirements** ("we must never lose a job", or you need
  a record of every delivery attempt) → SQS or RabbitMQ.
- **Replay, or several independent consumers of the same event stream** →
  Kafka.
- **Neither** → stay. Redis is not the bottleneck for a support inbox.

The migration is contained: `dispatch.py` (enqueue) and `app/worker/` (consume)
are the only modules that know a queue exists.

---

## 3. Why Postgres and not a NoSQL database

The data here is **relational, and its integrity constraints are the product**.

**The access patterns are joins.** The inbox is "conversations in this
workspace, filtered by status and assignee, sorted by last activity, each with
its contact, its assigned agent, its last message, and its unread count." In
Postgres that is a join and two batched aggregates. In a document store it is
either denormalisation — duplicating contact and agent data into every
conversation, then chasing every rename across documents — or several round
trips assembled in application code.

**Correctness properties are enforced by constraints, not by application code:**

| Constraint | What it prevents |
| --- | --- |
| `UNIQUE(conversation_id, seq)` | two messages claiming the same position under concurrency |
| Partial `UNIQUE(workspace_id, email_message_id)` | a webhook retry or mailbox re-poll duplicating a customer's email |
| `SELECT … FOR UPDATE` | two senders allocating the same `seq` |
| Foreign keys with `ON DELETE CASCADE` | orphaned messages when a workspace is removed |

Every one of these is a *database* guarantee. In an eventually-consistent store
each becomes application logic that is racy by construction — and "the customer
saw their message twice" is the kind of bug that is impossible to reproduce and
embarrassing to explain.

**Postgres also removed two dependencies.** Full-text search (`tsvector` + GIN)
and fuzzy matching (`pg_trgm`) mean the knowledge base needs no Elasticsearch,
and `JSONB` covers the genuinely schemaless field (message attachments) without
a second datastore. One database, three capabilities.

**Multi-tenancy is a filter, not a topology.** With `workspace_id` on every row
plus the right indexes, tenant isolation is a `WHERE` clause the query planner
handles well — and RLS is available later as defence in depth.

---

## 4. Where NoSQL would genuinely be better

Being fair to the alternatives, because "Postgres always" is as unthinking as
"Mongo always".

| Store | Where it wins | Would it help here? |
| --- | --- | --- |
| **Cassandra / DynamoDB** | Write-heavy, append-only, partitionable by key; linear scale-out; multi-region writes | Genuinely, for `messages` at very large scale — messages are append-only and naturally partition by conversation. But not before hundreds of millions of rows, and it costs the `seq` uniqueness guarantee |
| **MongoDB** | Varying document shapes, deep nesting, rapid schema churn | No. The schema here is stable and relational; the flexibility would be paid for in lost constraints |
| **Elasticsearch** | Relevance ranking, faceting, fuzzy search at scale | Later, yes — once the KB is large or search needs tuned ranking. Postgres FTS + trigram is enough at this size and is one less system |
| **Redis (as a primary store)** | Sub-millisecond reads of hot data | Already used for exactly that: presence, counters, queue |
| **ClickHouse / DuckDB** | Analytical scans over event data | Yes, when the analytics dashboard arrives — response-time and volume aggregates over millions of messages are a columnar workload, not an OLTP one |

### When to introduce them

The honest trigger for each, in the order they would arrive:

1. **Elasticsearch (or pgvector first)** — when knowledge-base search quality
   becomes a product complaint, or semantic retrieval is needed for AI
   grounding. *pgvector is the cheaper first move: same database, no new
   system.*
2. **A columnar store** — when analytics queries start competing with
   transactional load. The tell is analytics dashboards making the inbox slow.
3. **A wide-column store for `messages`** — only when Postgres partitioning has
   been exhausted, i.e. billions of rows or a genuine multi-region write
   requirement. The tell is that `messages` writes are the bottleneck *after*
   read replicas and partitioning.

The general rule applied throughout: **add a datastore when a workload's access
pattern is fundamentally different, not when the current one is merely
inconvenient.** Every new store is a new failure mode, a new backup policy, and
a new consistency question at its boundary.

---

## 5. Service-based architecture

### The current split, and its principle

Three deployables: **frontend**, **API**, **worker** — split by *how they
scale*, not by domain.

- The frontend scales with page traffic and belongs on a CDN.
- The API scales with concurrent users and sockets.
- The worker scales with background work, and its jobs have completely
  different time profiles: a 30-second Anthropic call must never occupy a
  request-handling process.

Note what is deliberately *not* split. Socket.IO runs inside the API rather than
as a fourth service, because both need identical authentication and session
state; separating them would introduce a network hop purely to share what they
already have in-process.

### Why not microservices per domain

A conversations service, a knowledge-base service, an email service, and an
identity service would mean four repositories, four deploys, and network calls
where a function call and a join used to be — and the tenant-isolation check
that currently sits in one dependency would be duplicated four times, with four
chances to get it wrong.

Microservices buy **independent deployability and independent scaling**. Neither
is worth paying for at this size, and both are recoverable later — the strict
`routes → services → models` layering means a service boundary can be drawn
along an existing seam rather than carved out of tangled code.

### When to split the worker

The signal is when **one job's failure or load profile starts hurting the
others**, in this order:

| Split off | Trigger |
| --- | --- |
| `poll_inbox` | It is a singleton (`unique=True`), so it cannot parallelise. Scaling the worker for send volume adds idle pollers and no polling capacity. It also disappears entirely once inbound moves to webhooks |
| `generate_summary` / AI jobs | Different resource shape — 30 seconds of waiting on a third party — and it wants its own cost budget, its own rate limit, and its own alerting. An AI backlog must never delay customer replies |
| `send_email` | Stays as the core worker: highest volume, cleanest fan-out |

The principle worth stating: **split along axes of independent scaling or
independent failure, not along domain boundaries.** Four services because there
are four job types is cargo-culting. One service for the poller because it is a
singleton is a real reason.

### When to split the API

Later than most teams do it. The first genuine candidate is the **public
surface** — the help centre and widget endpoints — because it has a different
traffic shape (unauthenticated, cacheable, spiky, and reachable by anyone) and
different security requirements from the authenticated dashboard API. Splitting
it would let the public side scale and be rate-limited independently, and would
shrink the attack surface of the authenticated service.

---

## 6. Horizontal scaling and load balancing

**No custom load balancer, deliberately.** The platform (Railway, or an
ALB/Fly/Render equivalent) terminates TLS and round-robins across replicas.
Re-implementing that is not application work.

What *is* application work is making the API safely balanceable, and that is
done:

| Property | Consequence |
| --- | --- |
| No server-side session state — JWT carries identity, re-validated per request | any replica serves any request |
| Socket.IO Redis manager | cross-replica message delivery |
| Presence in Redis with TTL | dead replicas' users expire |
| **WebSocket-only transport** | **no sticky sessions required** — the single most important scaling decision in the realtime layer, and one line of configuration |
| Rate limits in Redis | limits are global, not per-replica |

**To scale the API:** raise the replica count. One uvicorn process per container
rather than `--workers`, because asyncio is single-core-bound anyway and one
process per container keeps the memory footprint and the failure domain
legible.

**To scale the worker:** raise the replica count. Fan-out jobs distribute
naturally and cron jobs are deduplicated by `arq`.

**What blocks it today** is not the topology but the database: the unsized
connection pool combined with `max_jobs=20`, and Postgres' connection ceiling
at three or more API replicas. Size the pool, then put PgBouncer in front.
That order matters — adding replicas before fixing pooling makes the problem
arrive sooner, not later.
