# Architecture & Decisions

> Living document. Trade-offs and "what I skipped and why" are captured here as the build progresses.

## Overview

InterCom is a multi-tenant customer-communication platform. Three deployables:

- **Frontend** — Next.js (App Router, TypeScript) on Vercel: agent dashboard, embeddable chat
  widget, and the public knowledge base.
- **API** — Python FastAPI + `python-socketio` on Railway: REST + real-time (WebSocket) surface.
- **Worker** — Python (arq) on Railway: async jobs (AI summaries, outbound email, snooze reopen).

Shared state: **Postgres** (system of record) and **Redis** (job queue + Socket.IO pub/sub + rate limiting).

```
Browser ──HTTPS/WebSocket──▶ Next.js (Vercel) ──REST──▶ FastAPI (Railway) ──▶ Postgres
                                                     │  ▲                        │
                                               Socket.IO│  │ Redis pub/sub         │
                                                     ▼  │                         │
                                                   Redis ◀── queue ──▶ Worker ──▶ Claude / Postmark
```

## Multi-tenancy

`workspace` is the tenant boundary; every domain row carries `workspace_id`. Isolation is enforced
in a repository/service layer where **every query is scoped by the workspace from the caller's JWT**.
Optional Postgres RLS (session GUC) is documented as defense-in-depth.

## Real-time (live chat)

- Socket.IO rooms per conversation (`conversation:{id}`).
- Send → **persist to Postgres with a monotonic per-conversation `seq`** → publish to Redis →
  every API instance re-broadcasts to room members (horizontal scale).
- **Ordering:** clients render by `seq`, not arrival time.
- **Reconnection:** on reconnect the client sends its last-seen `seq`; server replays the gap.
- **Presence** (online/offline) via Redis TTL keys; **typing** via ephemeral room events;
  **read receipts** via last-read-seq broadcast.

## Email

**Provider-agnostic.** `EmailProvider` has two adapters, chosen by `EMAIL_PROVIDER`:

| Adapter | Inbound | Outbound | Needs |
| --- | --- | --- | --- |
| `imap` | IMAP poll (worker cron, 15s) | SMTP | any mailbox — no domain, no approval |
| `postmark` | webhook (push) | Postmark API | verified sender/domain |

Both normalise to `InboundEmail`, so routing and threading are written once.

### Multi-tenant routing

One mailbox (or one Postmark server) serves **every** workspace. Each workspace gets an
`inbound_key` generated at signup, and is addressed with a plus-tag:

```
support+acme@yourdomain.com    → workspace "acme"
support+globex@yourdomain.com  → workspace "globex"
```

Onboarding a workspace therefore requires **no change at the email provider**. Customers connect
their own `support@theircompany.com` by forwarding it to that address — the same model Intercom,
Zendesk and Help Scout use, because receiving mail for a domain you don't control is impossible by
design. Replies go out as the workspace name with `Reply-To` set to their real support address.

Resolution order when routing an inbound message:
1. plus-tag on `Delivered-To` / `OriginalRecipient` (survives `To:` rewriting)
2. plus-tag on `To:` / `Cc:`
3. **`In-Reply-To` / `References`** → inherit the workspace from the thread (covers forwarders that
   strip the tag)
4. otherwise: logged and dropped — never guessed into the wrong tenant

### Threading & safety

Replies carry `In-Reply-To` and the accumulated `References` chain, and the sent `Message-ID` is
stored so the customer's reply threads back. A partial unique index on
`(workspace_id, email_message_id)` makes inbound **idempotent** — a webhook retry or mailbox re-poll
cannot duplicate a message. Inbound HTML is sanitised with `bleach` before it can reach the
dashboard. Outbound is **queued** to the worker so a slow SMTP/API call never blocks an agent
request, with an inline fallback when Redis is unavailable.

## AI (summarization)

Worker calls Claude to summarize long conversations (what the user wants / what's been tried / status).
Summaries are cached on the conversation row and regenerated past a message threshold. Context is
windowed for cost; calls have a timeout and a graceful fallback.

## Security

JWT auth + RBAC (admin/agent), workspace-scoped queries (tenant isolation), HTML sanitization (bleach)
for email/KB/chat content, Postmark webhook signature verification, Redis rate limiting on public
endpoints, secrets in env.

## Scaling notes (production)

- Postgres connection pooling (PgBouncer / Supavisor) in front of serverless-ish workloads.
- Read replicas for analytics queries; more worker replicas for AI/email throughput.
- Upgrade the queue broker if volume warrants; add dead-letter handling.

## Trade-offs / deferred

- **Socket.IO + Redis** over a hand-rolled WebSocket server — faster to build, batteries-included
  reconnection/acks; trade-off is less low-level control.
- Deferred stretch items: SLA tracking, webhooks/API, AI auto-reply drafts (documented, not built).

_(Sections are expanded as each feature lands.)_
