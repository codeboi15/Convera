# High-Level Design

How InterCom is put together: the services, the data, and the path a message
takes through the system.

- [1. System context](#1-system-context)
- [2. Services](#2-services)
- [3. Data model](#3-data-model)
- [4. Request flows](#4-request-flows)
- [5. Real-time design](#5-real-time-design)
- [6. Queue design](#6-queue-design)
- [7. Multi-tenancy and security](#7-multi-tenancy-and-security)
- [8. Deployment topology](#8-deployment-topology)
- [9. Scaling path](#9-scaling-path)

Related reading: [TRADEOFFS.md](TRADEOFFS.md) for why these choices were made,
[SYSTEM_DESIGN.md](SYSTEM_DESIGN.md) for the datastore and service-boundary
reasoning, [DEPLOYMENT.md](DEPLOYMENT.md) for operating it.

---

## 1. System context

Four kinds of client talk to one API.

```
   End customer                      Support agent
        │                                  │
  ┌─────┴──────┐                    ┌──────┴───────┐
  │ Chat widget│                    │  Dashboard   │
  │ (iframe on │                    │  (inbox, KB, │
  │ their site)│                    │   settings)  │
  └─────┬──────┘                    └──────┬───────┘
        │                                  │
        │      ┌────────────────────┐      │
        └──────┤   InterCom API     ├──────┘
               │  REST + Socket.IO  │
   ┌───────────┤                    ├───────────┐
   │           └─────────┬──────────┘           │
   │                     │                      │
Public help          Postgres · Redis      Inbound email
centre (SEO)                                (customer's
                                            mail client)
```

The same conversation store backs every channel: a chat message and an email
are both rows in `messages`, differing only by `channel` on the parent
conversation. That is what makes a genuinely unified inbox possible rather than
two inboxes drawn side by side.

---

## 2. Services

Three deployables, split by **how they scale**, not by domain.

| Service | Stack | Responsibility | Scales with |
| --- | --- | --- | --- |
| **Frontend** | Next.js 14 (App Router, TS), Tailwind, Tiptap | Dashboard, embeddable widget, public help centre | Page traffic (edge/CDN) |
| **API** | Python, FastAPI, `python-socketio` | REST + WebSocket; all business logic | Concurrent users and sockets |
| **Worker** | Python, `arq` | Mailbox polling, outbound email, AI summaries, snooze expiry | Background work volume |

The API mounts Socket.IO alongside FastAPI in one ASGI app rather than running
a fourth service, because both need the same authentication and the same
session state — separating them would mean a network hop to share it.

Inside the API, layering is strict and load-bearing:

```
app/api/routes/   HTTP concerns only — parsing, status codes, auth dependencies
app/services/     business logic
app/models/       SQLAlchemy models
app/realtime/     Socket.IO server, event fan-out, presence
app/worker/       queue definitions and jobs
```

The same service functions are called from **three** entry points — REST
handlers, Socket.IO event handlers, and worker jobs. `add_message()` is called
by all three. If that logic lived in the route, the socket path would need its
own copy and the two would drift.

---

## 3. Data model

```
workspaces ──┬── workspace_members ── users
             │
             ├── contacts ──────┐
             │                  │
             ├── conversations ─┴── messages
             │
             ├── kb_categories ── kb_articles
             │
             └── invites
```

Every tenant-owned table carries `workspace_id`, including `messages` where it
is technically derivable through `conversation_id`. That denormalisation is
deliberate: tenant-scoped queries never need a join, and the unique index that
makes inbound email idempotent can exist at all.

**Key columns**

| Table | Column | Purpose |
| --- | --- | --- |
| `conversations` | `channel` | `chat` or `email` — the only difference between the two channels |
| | `status` | `open` / `snoozed` / `resolved` |
| | `message_count` | high-water mark; also the `seq` allocator |
| | `email_last_message_id` | newest `Message-ID` on the thread, so replies thread correctly |
| | `ai_summary`, `ai_summary_message_count` | cached summary and the point it was generated at |
| `messages` | `seq` | monotonic per-conversation ordering key |
| | `email_message_id` | RFC 5322 `Message-ID`, the idempotency key for inbound mail |
| `workspaces` | `inbound_key` | plus-address tag that routes mail to this tenant |
| | `custom_domain` | host that serves this workspace's help centre |

**Indexes that matter**

| Index | Serves |
| --- | --- |
| `UNIQUE(conversation_id, seq)` | ordering guarantee — a duplicate `seq` is impossible |
| Partial `UNIQUE(workspace_id, email_message_id) WHERE email_message_id IS NOT NULL` | inbound idempotency, without indexing the chat messages that have no header |
| `last_message_at`, `status`, `channel`, `assignee_id` | the inbox list and its filters |
| GIN `to_tsvector(title ‖ body_text)` | knowledge-base full-text search |
| GIN `lower(title) gin_trgm_ops` | typo tolerance ("refnd" → "refund") |

Schema changes ship as Alembic migrations (`0001_initial_schema` →
`0004_custom_domains`), forward-only.

---

## 4. Request flows

### 4.1 Live chat message

```
visitor types
  │
  ├─▶ socket.emit("send_message")
  │      │
  │      ├─ authorise: widget token → this contact owns this conversation?
  │      ├─ next_seq()  SELECT message_count FOR UPDATE  (per-conversation lock)
  │      ├─ INSERT message                               ← durable first
  │      ├─ COMMIT
  │      └─ emit "message:new"  → conversation room       ← broadcast second
  │                "inbox:message" → workspace room
  │
  └─◀ ack with the persisted message (sender reconciles its optimistic copy)
```

Persist-then-broadcast is the ordering guarantee: the database decides order,
not network timing.

### 4.2 Inbound email

```
customer emails support+acme@gmail.com
  │
  ├─ worker cron (every 15s) polls IMAP           [or provider webhook]
  ├─ parse → InboundEmail (headers, text, html)
  ├─ resolve tenant:
  │     1. plus-tag on a recipient address
  │     2. else the thread it replies to (In-Reply-To / References)
  │     3. else drop, with a warning log
  ├─ idempotency: seen this Message-ID for this workspace? → stop
  ├─ find conversation via threading headers, else create one
  ├─ sanitise HTML (bleach) → INSERT message
  └─ broadcast to the agent inbox over Socket.IO
```

Tier 2 is what survives forwarders that strip the plus-tag — which is what real
customers' mail servers do.

### 4.3 Outbound reply

```
agent sends from the dashboard
  │
  ├─ INSERT message (source of truth)
  ├─ enqueue_reply(message_id)        ← only the ID crosses the queue
  └─ 200 returned immediately          ← agent never waits on the mail provider
        │
   worker picks up
        ├─ re-read the message from Postgres  ← always current, never stale
        ├─ build headers: In-Reply-To, References, Reply-To = workspace address
        ├─ provider.send()  (Mailjet over HTTPS)
        └─ store the returned Message-ID so the customer's reply threads back
```

Retries are safe because the `Message-ID` unique index makes redelivery a
no-op. Idempotency lives in Postgres, which is the only component that can
actually enforce it.

### 4.4 AI reply draft

```
agent clicks "AI draft"
  │
  ├─ rate limit: 60/hour per workspace (paid API call)
  ├─ build retrieval query: last 3 customer messages + conversation subject
  ├─ extract distinctive keywords, search each, rank by hit count
  ├─ load the top 3 articles, truncate to 1200 chars each
  ├─ prompt Claude: transcript + articles + grounding rules
  └─ return draft + the articles it used → agent edits → agent sends
```

Nothing is ever sent automatically. On any failure the endpoint returns 503 and
the composer stays exactly as usable as before.

### 4.5 Custom domain

```
workspace enters help.acme.com
  ├─ we show the TXT + CNAME records to add
  ├─ "Verify" → real DNS TXT lookup (dnspython)
  ├─ verified → DomainProvider registers the host and TLS is issued
  └─ live: request with Host: help.acme.com
        └─ Next.js middleware resolves host → workspace slug
           and rewrites  /  →  /kb/acme,  /article → /kb/acme/article
```

The rewrite means one set of pages serves both the platform URL and the
customer's branded domain — there is no second implementation to keep in sync.

---

## 5. Real-time design

Everything here follows from one requirement: **the API must be stateless**, so
any instance can serve any request.

| Concern | Mechanism |
| --- | --- |
| Cross-instance delivery | `socketio.AsyncRedisManager` — a message published on instance A reaches a socket held by instance B |
| Rooms | `conversation:{id}` for a thread, `workspace:{id}` for inbox-level updates |
| Presence | Redis keys with a TTL, refreshed by a 25s client heartbeat, so a crashed instance's users expire on their own |
| Authentication | Handshake carries a JWT (agent) or widget token (visitor); returning `False` rejects before the socket joins any room |
| Revocation | Membership is re-checked in a background task that disconnects invalid sockets — the handshake must not wait on a database round-trip |
| **No sticky sessions** | The client is configured `transports: ["websocket"]`. Socket.IO's HTTP long-polling fallback spans multiple requests and therefore needs session affinity; disabling it removes that requirement entirely |
| Ordering | Monotonic `seq` per conversation, allocated under `SELECT … FOR UPDATE`, with `UNIQUE(conversation_id, seq)` as the backstop |
| Gap recovery | On every reconnect the client re-joins with its highest `seq`; the server replays everything after it |

Broadcast failures are caught and logged rather than raised — a realtime
problem must never fail the HTTP request that triggered it.

---

## 6. Queue design

`arq` over Redis. What goes on the queue is anything that talks to a third
party or takes unbounded time.

| Job | Trigger | Concurrency |
| --- | --- | --- |
| `send_email` | enqueued per agent reply | fans out across workers |
| `poll_inbox` | cron, every 15s | `unique=True` — exactly one worker per tick |
| `generate_summary` | enqueued on demand | fans out |
| `reopen_snoozed` | cron, every 5 min | `unique=True` |

Two properties worth naming:

- **Only the ID crosses the queue.** The worker re-reads from Postgres, so a
  job that waits a minute still sends current state.
- **Cron is safe to scale.** `arq`'s `cron(unique=True)` derives a
  deterministic job ID from the scheduled time, so adding worker replicas does
  not double-fire scheduled jobs.

If Redis is unreachable, `enqueue_reply` falls back to sending inline so local
development works without a worker running. That fallback is a development
convenience and is called out as a production risk in
[TRADEOFFS.md](TRADEOFFS.md).

---

## 7. Multi-tenancy and security

`workspace` is the tenant boundary.

- Every tenant table carries `workspace_id`; every query is scoped by the
  workspace resolved from the caller's token.
- **The token's workspace claim is re-validated against `workspace_members` on
  every request.** A forged or stale claim cannot reach another tenant's data,
  over REST *or* WebSocket.
- Roles are `admin` and `agent`, enforced by a dependency on the routes that
  mutate team or workspace state.
- Passwords are bcrypt, with the 72-byte truncation handled explicitly.
- Login returns one message for both unknown email and wrong password, so the
  endpoint cannot be used to enumerate users.
- All untrusted HTML — knowledge-base bodies from the editor, and inbound email
  — is sanitised with `bleach` **before it is stored**, so the public help
  centre and the dashboard can never render a script.
- Public endpoints carry Redis-backed rate limits; see the table in the README.

---

## 8. Deployment topology

```
Vercel                     Railway
┌──────────────┐          ┌──────────────┐   ┌──────────────┐
│  Next.js     │──REST───▶│  API (web)   │──▶│  Postgres    │
│  · dashboard │◀─socket─▶│  FastAPI +   │   └──────────────┘
│  · widget    │          │  Socket.IO   │   ┌──────────────┐
│  · help site │          └──────┬───────┘──▶│  Redis       │
└──────────────┘                 │           └──────┬───────┘
       ▲                         │                  │
       │                  ┌──────┴───────┐          │
  custom domains          │ Worker (arq) │◀─queue───┘
  (help.acme.com)         └──────┬───────┘
                                 ▼
                    Gmail IMAP (in) · Mailjet (out) · Claude
```

Both Railway services deploy from the same repository with different start
commands (`Procfile`): `web` runs uvicorn, `worker` runs arq.

---

## 9. Scaling path

Written as thresholds rather than aspirations — each entry is the *next* thing
that breaks, in order.

| Load | What breaks | Fix |
| --- | --- | --- |
| ~15 concurrent worker jobs | DB pool exhaustion — `max_jobs=20` exceeds the unsized default pool of 5+10 | Size the pool explicitly, or lower `max_jobs` |
| 3+ API replicas | Postgres connection ceiling | PgBouncer |
| Any multi-replica deploy | Migrations run in the web start command, so replicas race | Move to a release/pre-deploy step |
| Sustained send failures | No dead-letter queue; failures vanish into logs | DLQ + alerting |
| Inbound volume beyond one mailbox | IMAP is single-consumer by construction | Provider webhooks (already built) |
| Large inboxes | Inbox search is `LIKE '%…%'` — sequential scan | Give it the same `tsvector` treatment as the KB |
| Tens of millions of messages | Table size | Partition `messages` by workspace or time |

Horizontal scaling works today for both the API (stateless, Redis-backed
sockets, no sticky sessions) and the worker (fan-out jobs, deduplicated cron).
The limits above are about the datastore, not the application topology.
