# InterCom

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

### Documentation

| Document | What's in it |
| --- | --- |
| [docs/HLD.md](docs/HLD.md) | High-level design — services, schema, request flows, real-time and queue design |
| [docs/SYSTEM_DESIGN.md](docs/SYSTEM_DESIGN.md) | Why Redis, why Postgres over NoSQL, how each scales, service boundaries |
| [docs/TRADEOFFS.md](docs/TRADEOFFS.md) | Every decision and what it cost; known limitations; what's next |
| [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) | Deploying and operating it |
| [docs/CUSTOM_DOMAINS.md](docs/CUSTOM_DOMAINS.md) | Custom domains and SSL, end to end |

---

## Architecture

Three deployables over shared Postgres and Redis.

```
        ┌──────────────────────────────────────────────┐
        │  Next.js  (Vercel)                           │
        │  dashboard · chat widget · public help centre│
        └───────────────┬──────────────────────────────┘
                        │  REST + WebSocket
        ┌───────────────▼──────────────────────────────┐
        │  API  (Railway)                              │
        │  FastAPI + Socket.IO — one ASGI app          │
        └───┬──────────────────────────────────┬───────┘
            │                                  │
     ┌──────▼───────┐                  ┌───────▼───────┐
     │  Postgres    │                  │  Redis        │
     │  everything  │                  │  queue ·      │
     │  durable     │                  │  pub/sub ·    │
     └──────▲───────┘                  │  rate limits ·│
            │                          │  presence     │
            │                          └───────┬───────┘
        ┌───┴──────────────────────────────────▼───────┐
        │  Worker  (Railway, arq)                      │
        │  mail polling · sending · AI · snooze expiry │
        └──────────────┬───────────────────────────────┘
                       ▼
        Gmail IMAP (in) · Mailjet (out) · Claude
```

| Service | Stack | Responsibility | Scales with |
| --- | --- | --- | --- |
| **Frontend** | Next.js 14, TypeScript, Tailwind, Tiptap | Dashboard, embeddable widget, public help centre | Page traffic |
| **API** | Python, FastAPI, `python-socketio` | REST + real-time; all business logic | Concurrent users and sockets |
| **Worker** | Python, `arq` | Mailbox polling, outbound email, AI jobs, snooze expiry | Background work |

### The four ideas that matter

**One conversation store, two channels.** A chat message and an email are both
rows in `messages`; only `channel` on the parent conversation differs. That is
what makes the inbox genuinely unified rather than two lists side by side.

**Persist, then broadcast.** Messages are written to Postgres before they are
fanned out over Socket.IO, and each gets a monotonic per-conversation `seq`
allocated under a row lock with a `UNIQUE(conversation_id, seq)` backstop. The
database decides order, not network timing — and a reconnecting client asks for
"everything after seq N" to recover the gap.

**Stateless API.** No session state lives in a process: identity is a JWT
re-validated per request, sockets fan out through Redis, and presence is a Redis
key with a TTL. The client uses WebSocket-only transport, so **no sticky
sessions are needed** and any replica can serve any socket.

**Vendors behind interfaces.** `EmailProvider` and `DomainProvider` are abstract
bases selected by an environment variable. Outbound email moved Postmark → Brevo
→ SendGrid → Mailjet during the build; each switch was configuration only.

Schema, indexes, request flows, and failure handling are in
[docs/HLD.md](docs/HLD.md).

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

Plus one stretch feature:

| Stretch | Notes |
| --- | --- |
| **AI reply drafts** | Retrieval-augmented: drafts grounded in the workspace's own published articles, with the agent always in the loop |

Beyond the requirements: contact avatars and unread counts, keyboard-first
composer, skeleton loading states, XSS sanitisation on every untrusted HTML
path, and security headers (widget framable anywhere, dashboard `SAMEORIGIN`).

---

## Multi-tenancy and security

`workspace` is the tenant boundary. Every tenant row carries `workspace_id`, and
**the token's workspace claim is re-validated against `workspace_members` on
every request** — over REST *and* WebSocket — so a forged or stale claim cannot
reach another tenant's data.

- Passwords: bcrypt, with the 72-byte truncation handled explicitly.
- No user enumeration: one message for unknown email and wrong password.
- All untrusted HTML (knowledge-base bodies, inbound email) is sanitised with
  `bleach` **before storage**, so nothing can render a script.
- Webhooks authenticate with a shared secret compared in constant time.

### Rate limiting

Every endpoint reachable without an account has a budget, enforced with Redis
counters keyed on the caller's address (`X-Forwarded-For`, since the platform
terminates the connection). Over budget returns `429` with `Retry-After`;
allowed responses carry `X-RateLimit-Remaining`.

| Endpoint | Budget | Keyed on |
| --- | --- | --- |
| `POST /api/auth/login` | 10/min | IP |
| `POST /api/auth/signup` | 5/hour | IP |
| `POST /api/auth/refresh` | 60/min | IP |
| `POST /api/team/invites/accept` | 10/hour | IP |
| `POST /api/widget/session` | 20/min | IP |
| `GET /api/widget/suggestions` | 60/min | IP |
| `GET /api/public/kb/*/search` | 60/min | IP |
| `POST /api/webhooks/postmark/inbound` | 300/min | IP |
| `POST /api/conversations/*/summary` | 10/hour | **workspace** |
| `POST /api/conversations/*/draft` | 60/hour | **workspace** |

The two AI endpoints are keyed on the workspace rather than the caller: they are
the only ones whose abuse costs money, and one tenant should not be able to
exhaust another's allowance. The limiter **fails open** — if Redis is
unreachable, requests are served rather than rejected. That trade is argued in
[docs/TRADEOFFS.md](docs/TRADEOFFS.md).

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

Open http://localhost:3000, create a workspace, then use
**Settings → Install the chat widget** to open the demo page.
[`examples/widget-install.html`](examples/widget-install.html) shows the
one-tag installation on a plain HTML page.

Tests:

```bash
cd apps/backend && pip install -r requirements-dev.txt && pytest
```

---

## Configuration

Every value is read from the environment in exactly one place per service —
`apps/backend/app/core/config.py` and `apps/frontend/src/lib/config.ts` — so the
same build runs locally and in production.

Backend values are read at **runtime** (restart to apply). Frontend
`NEXT_PUBLIC_*` values are inlined at **build time** (redeploy to apply).

See [`apps/backend/.env.example`](apps/backend/.env.example),
[`apps/frontend/.env.example`](apps/frontend/.env.example), and
[docs/DEPLOYMENT.md](docs/DEPLOYMENT.md).

---

## Verification

Each feature was exercised against the real database and, once deployed, against
the live API — not mocks. Rate limiting and reply-draft retrieval have committed
`pytest` suites; everything else was verified with integration scripts, which is
acknowledged as the wrong long-term trade in
[docs/TRADEOFFS.md](docs/TRADEOFFS.md).

| Area | Checks |
| --- | --- |
| Auth, RBAC, tenant isolation | 16 |
| Realtime chat, ordering, gap recovery | 12 |
| Email routing, threading, idempotency | 18 |
| Knowledge base and public surfaces | 22 |
| AI windowing, caching, fallback | 18 |
| Hybrid search including typos | 8 |
| Custom domains and host routing | 29 |
| Outbound provider adapters and failure paths | 11 |
| Rate limiting (`pytest`, committed) | 10 |
| Reply-draft retrieval and grounding (`pytest`, committed) | 13 |
| Frontend ↔ backend API contract | 16 |
| **Production (deployed stack)** | **25** |

Notable properties covered: a forged workspace claim is rejected over both REST
and WebSocket; drafts never appear on any public surface; a duplicate inbound
`Message-ID` cannot create a second message; concurrent sends produce strictly
increasing sequence numbers; and both AI paths degrade cleanly with no API key.

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
docs/                 HLD, system design, trade-offs, deployment, custom domains
examples/             one-tag widget installation example
infra/                local Postgres and Redis
```
