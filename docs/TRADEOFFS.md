# Trade-offs

Every decision below cost something. This document is about what was given up,
not only what was gained — including the places where the trade turned out
worse than expected.

- [1. Decisions](#1-decisions)
- [2. Deliberately not built](#2-deliberately-not-built)
- [3. Known limitations](#3-known-limitations)
- [4. What I would do next](#4-what-i-would-do-next)

---

## 1. Decisions

### 1.1 Persist before broadcast

**Chosen:** write the message to Postgres, then fan it out over Socket.IO.

**Alternative:** broadcast optimistically and persist asynchronously — lower
latency, which is what a naive chat implementation does.

**Cost:** one database round-trip in the send path.

**Why:** with optimistic broadcast, two clients can legitimately disagree about
message order, and a write failure after a successful broadcast leaves a
message on screen that does not exist. Ordering is the property a support tool
cannot get wrong — an agent reading a thread out of order gives the wrong
answer. The round-trip is worth it.

### 1.2 A per-conversation write lock for ordering

**Chosen:** `SELECT message_count … FOR UPDATE` on the parent conversation row
to allocate `seq`, with `UNIQUE(conversation_id, seq)` as a backstop.

**Alternative:** a global sequence, a UUIDv7, or client timestamps.

**Cost:** writes to a single conversation serialise.

**Why:** a support conversation has perhaps two concurrent writers, so real
contention is nil, while different conversations stay fully parallel. In
exchange we get a gap-free ordering key that reconnect logic can use directly
(`give me everything after seq N`) — which timestamps cannot provide, because
clocks disagree and equal timestamps do not order.

### 1.3 WebSocket-only transport

**Chosen:** `transports: ["websocket"]` on the client.

**Alternative:** leave Socket.IO's HTTP long-polling fallback enabled.

**Cost:** clients on networks that block WebSocket cannot connect at all.

**Why:** the polling fallback spans multiple HTTP requests and therefore
requires sticky sessions at the load balancer. Dropping it makes any API
replica able to serve any socket, which is what makes horizontal scaling
straightforward. WebSocket support is effectively universal now; sticky
sessions are a permanent operational tax.

### 1.4 Plus-addressing for multi-tenant email

**Chosen:** one mailbox, `support+<key>@gmail.com`, with the tag selecting the
tenant and thread inheritance as a fallback.

**Alternative:** a mailbox or provider inbound domain per workspace.

**Cost:** every tenant's mail passes through one account, and its sending
reputation is shared.

**Why:** onboarding a workspace requires zero provider configuration — no
domain, no DNS, no manual step per customer. The fallback tier matters as much
as the tag: forwarders routinely strip plus-addressing, so mail that arrives
untagged is still routed by the thread it replies to.

### 1.5 Providers behind an interface

**Chosen:** `EmailProvider` and `DomainProvider` abstract bases, selected by an
environment variable.

**Alternative:** call the vendor SDK directly.

**Cost:** an indirection layer, and a lowest-common-denominator feature set.

**Why:** this one paid for itself immediately. Outbound email went Postmark →
Brevo → SendGrid → Mailjet during the build — Postmark needs a verified domain,
Brevo enforces an IP allowlist that cannot be disabled, SendGrid blocked
account creation. Each switch was an environment-variable change; routing,
threading, and the worker were never touched. The same shape lets custom-domain
TLS run through Vercel, Caddy, or a manual flow without the product knowing.

### 1.6 Redis for the queue

**Chosen:** `arq` on Redis, which was already present for Socket.IO fan-out.

**Alternative:** SQS, RabbitMQ, or a Postgres-backed queue.

**Cost:** Redis persistence is periodic, so a crash can lose enqueued jobs.

**Why:** zero additional infrastructure, and the worst case is one unsent
reply — recoverable, because the message is already durable in Postgres and can
be re-enqueued. The reasoning in full, including when this stops being the
right answer, is in [SYSTEM_DESIGN.md](SYSTEM_DESIGN.md).

### 1.7 At-least-once delivery, not exactly-once

**Chosen:** automatic retries plus a unique index on `Message-ID`.

**Alternative:** a transactional outbox with delivery bookkeeping.

**Cost:** a message can be *sent* twice if a send succeeds but recording it
fails.

**Why:** idempotency belongs in the one component that can enforce it. A
partial unique index makes redelivery a database no-op, which is far less
machinery than an outbox, and email is tolerant of the residual risk.

### 1.8 Rate limiting fails open

**Chosen:** if Redis is unreachable, allow the request.

**Alternative:** fail closed and reject.

**Cost:** an attacker who can take down Redis also removes the limits.

**Why:** a limiter that takes the entire API down when its datastore blips is
worse than the abuse it prevents. Availability wins for a support tool, where
being unreachable during an incident is the failure that actually hurts.

### 1.9 Fixed windows, not sliding

**Chosen:** one Redis counter per window.

**Cost:** a caller can spend a full budget at the end of one window and again at
the start of the next, so the true worst case is 2× the stated limit.

**Why:** a sliding window needs a sorted set per caller and per-request pruning.
Fixed windows are one integer. For abuse prevention, "roughly this many" is the
requirement.

### 1.10 Agent-in-the-loop AI

**Chosen:** AI writes drafts into the composer; the agent edits and sends.

**Alternative:** auto-reply when confidence is high.

**Cost:** no deflection — a human still handles every conversation.

**Why:** the failure mode of a wrong auto-reply is a customer given incorrect
information in your brand's voice, discovered later. Drafting removes most of
the typing while keeping the human accountable, and the UI names the articles
each draft drew from so the check is quick.

### 1.11 Lexical retrieval for AI grounding

**Chosen:** reuse the knowledge-base hybrid search (full-text + trigram) to
ground reply drafts.

**Alternative:** embeddings in pgvector.

**Cost:** vocabulary mismatch. A customer asking "can I get my money back?"
retrieves nothing from an article titled "How to request a refund" unless one
of them uses the other's word.

**Why:** Anthropic has no embeddings API, so semantic search means adding a
second AI vendor. Folding the conversation subject and several recent messages
into the query covers most real threads. When it retrieves nothing, the prompt
requires the model to ask a clarifying question rather than invent an answer —
so the failure is visible and safe rather than confidently wrong.

### 1.12 Polling for inbound mail

**Chosen:** IMAP poll every 15 seconds.

**Alternative:** provider inbound webhooks (also implemented, at
`/api/webhooks/postmark/inbound`).

**Cost:** up to 15 seconds of latency, and IMAP is single-consumer, so this
path cannot be parallelised.

**Why:** webhooks require a verified sending domain, which was not available.
Polling made a working multi-tenant email channel possible with one Gmail
account. The webhook path exists for when a domain does.

---

## 2. Deliberately not built

- **Analytics dashboard, SLA tracking, webhooks/API, canned responses** — the
  remaining stretch features. AI reply drafts was the one worth building: it
  composes the knowledge base and the AI plumbing that already existed rather
  than adding a fourth product surface.
- **LangChain / LangGraph** — summarisation and drafting are single model calls.
  A framework would add a dependency and an abstraction without adding
  capability.
- **Postgres row-level security** — the application-level scoping is
  consistent and tested. RLS is defence in depth, and worth adding, but it is
  not the first line of defence and would not have changed any behaviour here.
- **Per-workspace SMTP credentials** — would let replies come genuinely from
  `support@acme.com`. It needs a credential vault and a per-tenant onboarding
  flow; `Reply-To` gets most of the benefit at none of the cost.

---

## 3. Known limitations

**Outbound mail can land in spam.** The provider sends *as* a `gmail.com`
address it does not own, so DMARC cannot align and Gmail files it as spam —
correctly. Threading, headers, and DKIM are intact; the fix is a verified
sending domain, which is configuration rather than code.

**Replies come from the platform address.** `From` is the platform sender
carrying the workspace's name; `Reply-To` is the workspace's own support
address, so customer replies reach them.

**Gmail sends ~500/day.** Fine for a demo, not for production volume.

**Domain verification is point-in-time.** A domain whose DNS later lapses keeps
its verified flag until it is re-verified.

**TLS cannot be demonstrated on a reserved TLD.** The local custom-domain demo
runs over HTTP; no certificate authority will issue for `.test`, because nobody
can prove ownership of something nobody can own. The Vercel and Caddy adapters
cover the real path, and the deployed demo on a real domain has a real
certificate.

**`max_jobs=20` exceeds the database pool.** The worker allows 20 concurrent
jobs while the connection pool is left at SQLAlchemy's default 5 + 10 overflow.
Under a burst, jobs block for the pool timeout and then error. Not visible at
demo volume; it is the first thing that breaks under load.

**Migrations run in the web start command.** Convenient at one replica; at N
replicas they race on every deploy, and a failed migration takes down every
instance rather than one.

**No dead-letter queue.** After five attempts a failed job is gone, visible only
as a log line.

**The inline email fallback is a production risk.** If Redis is down, replies
send inline in the request. That is right for local development and wrong under
load, where it converts a queue outage into slow requests.

**Logging has no correlation ID.** Structured stdout logs with per-job
lifecycle lines exist, but a single request cannot be followed across API →
worker → provider. This is the weakest area of the build.

**Inbox search is unindexed.** `LIKE '%term%'` over subject and contact fields
means a sequential scan. The knowledge base got proper full-text search; the
inbox did not.

**Test coverage is narrow.** 23 committed `pytest` tests cover rate limiting and
reply-draft retrieval. Everything else was verified with integration scripts run
against the real database and the deployed API — the wrong trade for a
long-lived codebase, and the first thing to extend.

---

## 4. What I would do next

In priority order, judged by risk removed per hour spent.

1. **Correlation IDs and structured logs.** Stamp a request ID into a
   `contextvar`, include it in the log format, and pass it into every job. This
   is what makes the other operational gaps diagnosable.
2. **Fix the pool/`max_jobs` mismatch and move migrations to a release step.**
   Both are small and both are real.
3. **Dead-letter queue and alerting** on repeated job failure.
4. **A verified sending domain**, which fixes deliverability and unlocks
   inbound webhooks — removing the polling bottleneck at the same time.
5. **Extend the test suite** with a throwaway database, then wire it into CI.
6. **Analytics dashboard** — response and resolution times, busiest hours,
   agent volume. The data is already in `messages` and `conversations`.
7. **pgvector for retrieval**, which removes the vocabulary-mismatch limit on
   reply drafts and improves widget suggestions.
8. **Postgres RLS** as defence in depth behind the existing scoping.
