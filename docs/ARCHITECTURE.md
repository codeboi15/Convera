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

Postmark inbound webhook → verify → parse `Message-ID` / `In-Reply-To` / `References` →
match or create a conversation. Outbound replies are **enqueued** and sent by the worker with correct
threading headers; the returned `Message-ID` is stored for future matching.

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
