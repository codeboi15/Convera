# Deployment Guide

Self-contained context for deploying **InterCom** (repo: `codeboi15/Convera`). Everything needed to
finish or debug a deployment lives in this file.

---

## 1. What gets deployed

Three deployables from one monorepo. Each platform builds only its own subfolder.

| Service | Platform | Root directory | Start command |
| --- | --- | --- | --- |
| **API** (REST + Socket.IO) | Railway | `apps/backend` | `alembic upgrade head && uvicorn app.main:asgi --host 0.0.0.0 --port $PORT` |
| **Worker** (email poll, AI jobs) | Railway | `apps/backend` | `python -m app.worker.main` |
| **Frontend** (dashboard, widget, KB) | Vercel | `apps/frontend` | `npm run build` (auto) |

Plus two Railway plugins: **PostgreSQL** and **Redis**.

Build is auto-detected (Nixpacks reads `requirements.txt`); leave Railway's build command blank.

### Current state (2026-08-11)

- API deployed at `https://convera-production-a90e.up.railway.app` — **verified working**
- Postgres provisioned, migrated to revision `0002_email`
- Worker service: **not yet created**
- Frontend: **not yet deployed**
- Email env vars: **not yet set on Railway**

---

## 2. Configuration model

**No secrets are ever committed.** `.env` is gitignored; only `.env.example` (blank placeholders) is
in git.

- **Backend** reads config in exactly one place: `apps/backend/app/core/config.py` (Pydantic
  `Settings`). Precedence: **real env vars (Railway) > `.env` file (local only) > defaults**.
  Values are read at **runtime** — change a variable, restart the service.
- **Frontend** reads config in exactly one place: `apps/frontend/src/lib/config.ts`.
  `NEXT_PUBLIC_*` values are inlined at **build time** — changing one requires a **redeploy**, and
  they are visible in the browser bundle, so **never put secrets there**.

---

## 3. Railway variables (set on BOTH the API and Worker services)

Use Railway's project-level shared variables so both services stay in sync.

```bash
# Data — use Railway reference syntax so credential rotation is automatic
DATABASE_URL=${{Postgres.DATABASE_URL}}
REDIS_URL=${{Redis.REDIS_URL}}

# App
APP_ENV=production
DEBUG=false
JWT_SECRET=<openssl rand -hex 32>       # MUST NOT be the dev default

# CORS / links — set after the Vercel URL exists
FRONTEND_URL=https://<your-app>.vercel.app
CORS_ORIGINS=https://<your-app>.vercel.app

# Email channel (IMAP/SMTP adapter — no domain or provider approval needed)
EMAIL_PROVIDER=imap
EMAIL_INBOUND_ADDRESS=support.convera@gmail.com
EMAIL_FROM_NAME=Convera Support
IMAP_HOST=imap.gmail.com
IMAP_PORT=993
IMAP_USERNAME=support.convera@gmail.com
IMAP_PASSWORD=<gmail app password, no spaces>
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=support.convera@gmail.com
SMTP_PASSWORD=<gmail app password, no spaces>

# AI (add when available)
ANTHROPIC_API_KEY=
ANTHROPIC_MODEL=claude-sonnet-5
```

To switch to Postmark later, change only:
`EMAIL_PROVIDER=postmark`, `POSTMARK_SERVER_TOKEN`, `POSTMARK_FROM_EMAIL`,
`POSTMARK_INBOUND_SECRET`, and point Postmark's inbound webhook at
`https://<api>/api/webhooks/postmark/inbound?token=<POSTMARK_INBOUND_SECRET>`.

---

## 4. Vercel setup

1. New Project → import `codeboi15/Convera`
2. **Root Directory: `apps/frontend`** (critical — otherwise the build fails)
3. Framework: Next.js (auto-detected)
4. Environment variables:

```bash
NEXT_PUBLIC_API_URL=https://convera-production-a90e.up.railway.app
NEXT_PUBLIC_SOCKET_URL=https://convera-production-a90e.up.railway.app
NEXT_PUBLIC_APP_URL=https://<your-app>.vercel.app   # set after first deploy, then redeploy
```

5. Deploy → copy the URL → set `FRONTEND_URL` and `CORS_ORIGINS` on Railway → restart the API.

**Branch:** Settings → Git → Production Branch. Vercel and Railway **must track the same branch**,
otherwise frontend and backend drift apart.

---

## 5. Order of operations

1. Push code to the branch both platforms track
2. Railway: Postgres + Redis plugins → API service → Worker service
3. Set Railway variables (all except `FRONTEND_URL`/`CORS_ORIGINS`)
4. Deploy Vercel → get URL
5. Set `FRONTEND_URL` + `CORS_ORIGINS` on Railway → restart
6. Set `NEXT_PUBLIC_APP_URL` on Vercel → redeploy
7. Run the verification checklist below

---

## 6. Known issues & fixes

**`Internal Server Error` on signup, but `/api/health` is fine.**
Deployed code is older than the database schema. Migration `0002_email` added
`workspaces.inbound_key NOT NULL`; older code doesn't populate it, so every INSERT fails while reads
still work. **Fix: deploy current code.** Always deploy code before/with its migration.

**`SSL SYSCALL error: EOF detected` connecting to Postgres from outside Railway.**
The public proxy requires TLS. Append `?sslmode=require` to the public `DATABASE_URL`. The internal
URL (`*.railway.internal`) does not need it and is unreachable from outside Railway.

**Socket.IO connects but immediately drops.**
Do not perform slow I/O inside the Socket.IO `connect` handler — it exceeds the client's handshake
timeout. Membership is verified in a background task (`_verify_membership`) that disconnects invalid
sockets instead.

**Widget not appearing on an embedding site.**
`/widget` must be framable. `next.config.mjs` sets `frame-ancestors *` for `/widget` and
`Access-Control-Allow-Origin: *` for `/widget.js`, while the dashboard stays `SAMEORIGIN`.

**Worker not processing inbound email.**
The worker requires `REDIS_URL`. Without Redis, `enqueue_reply` falls back to sending inline, but the
IMAP poll cron never runs.

---

## 7. Verification checklist (run against the deployed URLs)

```bash
API=https://convera-production-a90e.up.railway.app
curl -s $API/api/health                    # {"status":"ok"}
curl -s $API/openapi.json | jq '.paths | keys | length'   # expect 23+
```

Then in the browser:

1. Sign up on the Vercel URL → lands in the inbox
2. Settings → copy the widget snippet → open `/demo?workspace=<slug>` → send a message →
   appears in the dashboard in real time (the "Live" pill is green)
3. Reload the demo page → chat history persists
4. Email `support.convera+<inbound_key>@gmail.com` → appears as a conversation within ~15s
   (requires the worker service) → reply from dashboard → arrives threaded
5. Invite a teammate → accept in a private window → confirm agent role restrictions
6. Second workspace cannot see the first's data

---

## 8. Security before submission

- Rotate the **Postgres password** (Railway → Postgres → regenerate); `${{Postgres.DATABASE_URL}}`
  updates automatically
- Rotate the **Gmail app password** and revoke the old one
- Confirm `JWT_SECRET` is a strong random value in production
- Confirm no `.env` file is tracked: `git check-ignore -v apps/backend/.env`
