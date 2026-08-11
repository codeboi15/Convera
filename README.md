# Convera

A multi-tenant customer communication platform: live chat, email, a unified
inbox, a knowledge base, AI conversation summaries and reply drafts, and custom
domains.

Built for the SuperProfile Member of Technical Staff assignment.

| | |
| --- | --- |
| **Dashboard** | https://convera-topaz.vercel.app |
| **API** | https://convera-production-a90e.up.railway.app |
| **Public help centre** | `/kb/<workspace-slug>` |
| **Widget demo page** | `/demo?workspace=<workspace-slug>` |
| **Support inbox** | `support.convera+<inbound-key>@gmail.com` (shown in Settings) |

**[docs/HLD.md](docs/HLD.md)** — architecture, schema, request flows, design
decisions, trade-offs, and scaling.

---

## Architecture

Three deployables over shared Postgres and Redis.

```
   Next.js (Vercel)  ──REST + WebSocket──▶  API (Railway)
   dashboard · widget                      FastAPI + Socket.IO
   · help centre                                │        │
                                           Postgres    Redis
                                                │        │
                                          Worker (Railway, arq)
                                                ▼
                        Gmail IMAP (in) · Mailjet (out) · Claude
```

| Service | Responsibility | Scales with |
| --- | --- | --- |
| **Frontend** — Next.js 14, TS, Tailwind, Tiptap | Dashboard, widget, public help centre | Page traffic |
| **API** — FastAPI, `python-socketio` | REST + real-time; all business logic | Concurrent users and sockets |
| **Worker** — `arq` | Mailbox polling, outbound mail, AI jobs, snooze expiry | Background work |

Four ideas do most of the work:

- **One conversation store, two channels.** Chat and email are both rows in
  `messages`; only `channel` differs. That is what makes the inbox genuinely
  unified rather than two lists side by side.
- **Persist, then broadcast.** Messages are written to Postgres before they fan
  out over Socket.IO, each with a monotonic per-conversation `seq`. The database
  decides order, not network timing.
- **Stateless API.** JWT re-validated per request, sockets fan out through
  Redis, presence is a Redis TTL. WebSocket-only transport means **no sticky
  sessions** — any replica serves any socket.
- **Vendors behind interfaces.** Outbound email moved Postmark → Brevo →
  SendGrid → Mailjet during the build; each switch was configuration only.

---

## What's built

All seven required features.

| # | Requirement | Notes |
| --- | --- | --- |
| 1 | **Auth & team management** | JWT access/refresh, workspace switching, invites, admin/agent RBAC, agent assignment |
| 2 | **Chat widget** | One `<script>` tag; iframe-isolated; typing indicators, presence, read receipts; history survives reload |
| 3 | **Email channel** | Inbound parsing, `Message-ID`/`In-Reply-To`/`References` threading, queued replies, idempotent redelivery |
| 4 | **Unified inbox** | Chat + email in one list; filter by channel/assignee/status/search; assign, snooze, resolve |
| 5 | **Knowledge base** | Rich-text editor, categories, draft/publish, public help centre with search, widget auto-suggest |
| 6 | **AI summarization** | Claude, with context windowing, caching, and fail-soft degradation |
| 7 | **Custom domains** | Real DNS verification, pluggable TLS, host-based routing |
| — | **AI reply drafts** *(stretch)* | Retrieval-augmented: grounded in the workspace's own published articles, agent always in the loop |

Multi-tenant throughout: every tenant row carries `workspace_id`, and the
token's workspace claim is re-validated against `workspace_members` on every
request — over REST *and* WebSocket. All untrusted HTML is sanitised before
storage, and every unauthenticated endpoint has a Redis-backed rate limit.
Details in [the HLD](docs/HLD.md#6-security).

---

## Running it locally

Prerequisites: Node 20+, Python 3.10+, Postgres, Redis.

```bash
# Data services (optional — or point the env at hosted instances)
docker compose -f infra/docker-compose.yml up -d

# Backend
cd apps/backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # fill in values
alembic upgrade head
uvicorn app.main:asgi --reload --port 8000

# Worker (separate terminal, needs REDIS_URL)
python -m app.worker.main

# Frontend
cd apps/frontend
npm install
cp .env.example .env.local
npm run dev
```

Open http://localhost:3000, create a workspace, then use **Settings → Install
the chat widget**. [`examples/widget-install.html`](examples/widget-install.html)
shows the one-tag installation on a plain HTML page.

Tests: `cd apps/backend && pip install -r requirements-dev.txt && pytest`

### Configuration

Every value is read from the environment in exactly one place per service —
`apps/backend/app/core/config.py` and `apps/frontend/src/lib/config.ts` — so the
same build runs locally and in production. Backend values apply at **runtime**
(restart); frontend `NEXT_PUBLIC_*` values are inlined at **build time**
(redeploy). See the two `.env.example` files for the full list.

Deployment is two Railway services from one repo (`Procfile`: `web` and
`worker`) plus Vercel for the frontend.

---

## Repository

```
apps/
  backend/            FastAPI + Socket.IO API and arq worker
    app/
      api/routes/     HTTP endpoints
      services/       business logic (auth, conversations, email, kb, ai, domains)
      models/         SQLAlchemy models
      realtime/       Socket.IO server, events, presence
      worker/         queue and scheduled jobs
      core/           config, db, security, rate limiting
    alembic/          migrations
    tests/            pytest suite
  frontend/           Next.js dashboard, widget, and public help centre
docs/HLD.md           architecture, schema, flows, decisions, trade-offs
examples/             one-tag widget installation example
infra/                local Postgres and Redis
```
