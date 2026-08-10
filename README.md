# InterCom

A multi-tenant customer-communication platform (an Intercom-style product): live chat widget,
email channel, unified inbox, knowledge base, AI conversation summaries, and custom domains.

Built for the SuperProfile "Member of Technical Staff" assignment.

## Architecture

```
Browser (dashboard / widget / public KB)
      │  HTTPS + WebSocket (Socket.IO)
      ▼
Next.js (Vercel) ──REST──▶ FastAPI API (Railway) ──▶ Postgres
                                │   ▲                    │
                          Socket.IO│                     │
                                ▼   │ Redis pub/sub       │
                              Redis ◀── queue ──▶ Python Worker ──▶ Claude / Postmark
Postmark inbound webhook ───────▶ FastAPI /webhooks/postmark/inbound
```

| Layer            | Tech                                                        |
| ---------------- | ----------------------------------------------------------- |
| Frontend         | Next.js 14 (App Router, TypeScript), Tailwind, Socket.IO client |
| Backend API      | Python, FastAPI, `python-socketio`, Uvicorn                 |
| Worker           | Python (same codebase), Redis-backed job queue              |
| Data             | Postgres (SQLAlchemy 2.0 + Alembic), Redis                  |
| Email            | Postmark (inbound webhook + outbound threading)             |
| AI               | Anthropic Claude                                            |
| Hosting          | Vercel (frontend) + Railway (api, worker, postgres, redis)  |

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the deeper design, trade-offs, and scaling notes.

## Repository layout

```
apps/
  backend/     FastAPI API + Socket.IO + Python worker (one package, two entrypoints)
  frontend/    Next.js app: dashboard, chat widget, public knowledge base
docs/          Architecture & decision records
infra/         Deployment config (Railway, docker-compose for local data services)
```

## Local development

Prerequisites: Node 20+, Python 3.10+ (3.9 works with `from __future__ import annotations`),
and a Postgres + Redis instance (Docker compose provided, or point env at Railway/Neon/Upstash).

```bash
# 1. Data services (if you have Docker)
docker compose -f infra/docker-compose.yml up -d

# 2. Backend
cd apps/backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env      # fill in values
alembic upgrade head
uvicorn app.main:asgi --reload --port 8000      # API + Socket.IO
python -m app.worker.main                       # worker (separate terminal)

# 3. Frontend
cd apps/frontend
npm install
cp .env.example .env.local
npm run dev
```

## Environment variables

See `apps/backend/.env.example` and `apps/frontend/.env.example`.

## Status

Work in progress — see the build log in commit history.
