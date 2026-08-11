# High-Level Design

Architecture, schema, flows, and the decisions behind them.

[1. Architecture](#1-architecture) · [2. Schema](#2-schema) ·
[3. Flows](#3-flows) · [4. Real-time](#4-real-time) · [5. Queue](#5-queue) ·
[6. Security](#6-security) · [7. Design decisions](#7-design-decisions) ·
[8. Trade-offs and limitations](#8-trade-offs-and-limitations)

---

## 1. Architecture

Three deployables over shared Postgres and Redis, split by **how they scale**,
not by domain.

```
        ┌──────────────────────────────────────────────┐
        │  Next.js  (Vercel)                           │
        │  dashboard · chat widget · public help centre│
        └───────────────┬──────────────────────────────┘
                        │  REST + WebSocket
        ┌───────────────▼──────────────────────────────┐
        │  API  (Railway) — FastAPI + Socket.IO        │
        └───┬──────────────────────────────────┬───────┘
            │                                  │
     ┌──────▼───────┐                  ┌───────▼───────┐
     │  Postgres    │                  │  Redis        │
     │  everything  │                  │  queue ·      │
     │  durable     │                  │  pub/sub ·    │
     └──────▲───────┘                  │  rate limits ·│
            │                          │  presence     │
        ┌───┴──────────────────────────┴───────────────┐
        │  Worker  (Railway, arq)                      │
        │  mail polling · sending · AI · snooze expiry │
        └──────────────┬───────────────────────────────┘
                       ▼
        Gmail IMAP (in) · Mailjet (out) · Claude
```

| Service | Responsibility | Scales with |
| --- | --- | --- |
| **Frontend** — Next.js 14, TS, Tailwind, Tiptap | Dashboard, widget, public help centre | Page traffic |
| **API** — FastAPI, `python-socketio` | REST + real-time; all business logic | Concurrent users and sockets |
| **Worker** — `arq` | Mailbox polling, outbound mail, AI jobs, snooze expiry | Background work |


---

## 2. Schema

```
workspaces ──┬── workspace_members ── users
             ├── contacts ──────┐
             ├── conversations ─┴── messages
             ├── kb_categories ── kb_articles
             └── invites
```

Every tenant table carries `workspace_id`, including `messages` where it is
derivable via `conversation_id`. That denormalisation means tenant-scoped
queries never need a join, and it lets the inbound-email idempotency index
exist at all.

**Columns that carry weight**

| Table | Column | Purpose |
| --- | --- | --- |
| `conversations` | `channel` | `chat` or `email` — the only difference between the two channels |
| | `status` | `open` / `snoozed` / `resolved` |
| | `message_count` | high-water mark, and the `seq` allocator |
| | `email_last_message_id` | newest `Message-ID` on the thread, so replies thread correctly |
| | `ai_summary`, `ai_summary_message_count` | cached summary and the point it was generated at |
| `messages` | `seq` | monotonic per-conversation ordering key |
| | `email_message_id` | RFC 5322 `Message-ID` — the idempotency key for inbound mail |
| `workspaces` | `inbound_key` | plus-address tag that routes mail to this tenant |
| | `custom_domain` | host that serves this workspace's help centre |

---

## 3. Flows

### Live chat message

```
socket.emit("send_message")
  ├─ authorise: does this widget token own this conversation?
  ├─ next_seq(): SELECT message_count FOR UPDATE   ← per-conversation lock
  ├─ INSERT message, COMMIT                        ← durable first
  └─ emit "message:new" → conversation room        ← broadcast second
          "inbox:message" → workspace room
  ◀ ack with the persisted message (sender reconciles its optimistic copy)
```

### Inbound email

```
customer emails support+acme@gmail.com
  ├─ worker cron polls IMAP every 15s          [or a provider webhook]
  ├─ parse headers, text, html
  ├─ resolve tenant:  1. plus-tag on a recipient
  │                   2. else the thread it replies to (In-Reply-To/References)
  │                   3. else drop, with a warning
  ├─ seen this Message-ID for this workspace? → stop
  ├─ find conversation via threading headers, else create
  ├─ sanitise HTML (bleach) → INSERT message
  └─ broadcast to the agent inbox
```

Tier 2 is what survives forwarders that strip the plus-tag — which is what real
customers' mail servers do.

### Outbound reply

```
agent sends
  ├─ INSERT message (source of truth)
  ├─ enqueue_reply(message_id)     ← only the ID crosses the queue
  └─ 200 immediately               ← agent never waits on the mail provider
      worker:
        ├─ re-read from Postgres   ← always current, never stale
        ├─ headers: In-Reply-To, References, Reply-To = workspace address
        ├─ provider.send()  (Mailjet, HTTPS)
        └─ store the returned Message-ID so the customer's reply threads back
```

### AI reply draft

```
agent clicks "AI draft"
  ├─ rate limit: 60/hour per workspace (paid call)
  ├─ query = last 3 customer messages + conversation subject
  ├─ extract keywords, search each, rank by hit count
  ├─ top 3 articles, 1200 chars each
  ├─ prompt Claude: transcript + articles + grounding rules
  └─ draft + cited articles → composer → agent edits → agent sends
```

Nothing is ever sent automatically. Any failure returns 503 and leaves the
composer exactly as usable as before.

### Custom domain

```
workspace enters help.acme.com
  ├─ show the TXT + CNAME records to add
  ├─ "Verify" → real DNS TXT lookup (dnspython)
  ├─ verified → DomainProvider registers the host, TLS is issued
  └─ live: Host: help.acme.com
        └─ Next.js middleware resolves host → slug, rewrites
           /  →  /kb/acme     and     /article  →  /kb/acme/article
```

One set of pages serves both the platform URL and the customer's branded
domain — no second implementation to keep in sync.

---

## 4. Real-time

Everything follows from one requirement: the API must be **stateless**, so any
instance can serve any request.

| Concern | Mechanism |
| --- | --- |
| Cross-instance delivery | `socketio.AsyncRedisManager` — a message published on instance A reaches a socket on instance B |
| Rooms | `conversation:{id}` for a thread, `workspace:{id}` for inbox updates |
| Presence | Redis keys with a TTL, refreshed by a 25s heartbeat, so a crashed instance's users expire on their own |
| Auth | JWT (agent) or widget token in the handshake; returning `False` rejects before the socket joins any room |
| Revocation | Membership re-checked in a background task that disconnects invalid sockets — the handshake must not wait on a DB round-trip |
| **No sticky sessions** | Client uses `transports: ["websocket"]`. The HTTP long-polling fallback spans multiple requests and needs session affinity; dropping it removes that requirement |
| Ordering | Monotonic `seq` under `SELECT … FOR UPDATE`, with `UNIQUE(conversation_id, seq)` as backstop |
| Gap recovery | On reconnect the client re-joins with its highest `seq`; the server replays everything after it |

Broadcast failures are caught and logged, never raised — a realtime problem
must not fail the request that triggered it.

---

## 5. Queue

`arq` over Redis. Anything that talks to a third party or takes unbounded time.

| Job | Trigger | Concurrency |
| --- | --- | --- |
| `send_email` | per agent reply | fans out across workers |
| `poll_inbox` | cron, 15s | `unique=True` — one worker per tick |
| `generate_summary` | on demand | fans out |
| `reopen_snoozed` | cron, 5 min | `unique=True` |

**Only the ID crosses the queue** — the worker re-reads from Postgres, so a job
that waits a minute still sends current state. **Retry-safety comes from the
schema**: the `Message-ID` unique index makes redelivery a no-op, so `arq`'s
default five retries are safe. **Cron is safe to scale**: `unique=True` derives
a deterministic job ID from the scheduled time, so extra worker replicas do not
double-fire.

---

## 6. Security

`workspace` is the tenant boundary. Every tenant row carries `workspace_id`, and
**the token's workspace claim is re-validated against `workspace_members` on
every request** — over REST *and* WebSocket — so a forged or stale claim cannot
reach another tenant's data.

- Passwords: bcrypt, 72-byte truncation handled explicitly.
- No user enumeration: one message for unknown email and wrong password.
- Roles `admin` / `agent`, enforced by a dependency on mutating routes.
- All untrusted HTML — KB bodies from the editor, and inbound email — is
  sanitised with `bleach` **before storage**, so nothing can render a script.
- Webhooks authenticate with a shared secret compared in constant time.

**Rate limits** — Redis counters keyed on `X-Forwarded-For` (the platform
terminates the connection). Over budget returns `429` with `Retry-After`.

| Endpoint | Budget | Keyed on |
| --- | --- | --- |
| `auth/login` · `auth/signup` · `auth/refresh` | 10/min · 5/hour · 60/min | IP |
| `team/invites/accept` | 10/hour | IP |
| `widget/session` · `widget/suggestions` | 20/min · 60/min | IP |
| `public/kb/*/search` | 60/min | IP |
| `webhooks/postmark/inbound` | 300/min | IP |
| `conversations/*/summary` · `conversations/*/draft` | 10/hour · 60/hour | **workspace** |

The AI endpoints are keyed on the workspace because they are the only ones
whose abuse costs money.

---

## 7. Design decisions

### 7.1 Why Postgres

The data is relational and its **integrity constraints are the product**.

Postgres also removed two dependencies: `tsvector` + `pg_trgm` mean the
knowledge base needs no Elasticsearch, and `JSONB` covers the one genuinely
schemaless field (attachments).

**Where NoSQL would genuinely be better, and when to introduce it:**

| Store | Wins at | Introduce when |
| --- | --- | --- |
| pgvector | Semantic retrieval | KB search quality becomes a complaint, or AI grounding needs it. *Cheapest first move — same database* |
| Elasticsearch | Relevance tuning, faceting at scale | pgvector is no longer enough |
| ClickHouse / DuckDB | Analytical scans | Analytics queries start competing with transactional load |
| Cassandra / DynamoDB | Append-only writes, linear scale-out | `messages` writes bottleneck *after* read replicas and partitioning — billions of rows, or multi-region writes. Costs the `seq` guarantee |
| MongoDB | Varying document shapes | Not here. The schema is stable and relational |

The rule applied throughout: **add a datastore when a workload's access pattern
is fundamentally different, not when the current one is merely inconvenient.**
Each new store is a new failure mode, backup policy, and consistency question.

### 7.2 Why Redis, and how it scales

Redis does four jobs — and one component doing four jobs is most of the
justification: pub/sub for cross-instance sockets (without it, adding a second
API replica silently breaks delivery for half your users), the job queue,
rate-limit counters (`INCR`+`EXPIRE`, atomic and O(1)), and presence.

**Limits, in the order they bite:** memory (the queue is in RAM; a backlog risks
eviction — set `maxmemory-policy noeviction`), durability (periodic persistence,
so a crash can lose enqueued jobs — acceptable because the *message* is durable
in Postgres and can be re-enqueued), single-threaded execution, and no consumer
groups in `arq`.

**Scaling ladder:** 
① add worker replicas against one Redis 
② replica + failover
③ **separate instances per role** (queue / pub-sub / limits)

---

## 8. Trade-offs and limitations

**Deliverability.** Mail sends *as* a `gmail.com` address it does not own, so
DMARC cannot align and Gmail files it as spam — correctly.


**No dead-letter queue.** After five attempts a failed job is gone, visible only
as a log line.

**The inline email fallback is a production risk.** If Redis is down, replies
send inline in the request — right for local development, wrong under load,
where it turns a queue outage into slow requests.


**Domain verification is point-in-time** — a domain whose DNS later lapses keeps
its verified flag until re-verified. And TLS cannot be shown on a reserved TLD:
the local `.test` demo runs over HTTP, because no CA will issue for a name
nobody can own. The deployed demo on a real domain has a real certificate.

