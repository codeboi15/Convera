# Custom Domains — How It Works & How to Demo It

A workspace can serve its public knowledge base from its own hostname
(`help.acme.com`) instead of the platform URL (`/kb/acme`). Both render the
same pages — only the hostname differs.

## Architecture

Four concerns, only one of which is platform-specific:

| Concern | Where it lives | Portable? |
| --- | --- | --- |
| Domain → workspace mapping | `workspaces.custom_domain` | ✅ |
| Ownership verification | `services/domains/verification.py` — real DNS TXT lookup | ✅ |
| Host-based routing | `apps/frontend/src/middleware.ts` | ✅ |
| **TLS certificate issuance** | `services/domains/providers.py` | 🔌 adapter |

Certificate issuance is the only part that needs a platform, so it sits behind
a `DomainProvider` interface selected by `DOMAIN_PROVIDER`:

| Provider | How the certificate is obtained |
| --- | --- |
| `manual` *(default)* | Operator adds the domain to their host; nothing is called |
| `caddy` | Caddy asks `GET /api/public/domains/authorize?domain=…` then issues a Let's Encrypt certificate on demand — **no vendor API involved** |
| `vercel` | `POST /v10/projects/{id}/domains`; Vercel issues and renews the certificate |

### Why verification exists

Without proof of ownership, any workspace could claim `help.google.com` and the
platform would serve content on it. Verification requires a TXT record only the
real owner can publish. **Unverified domains never serve content** and are
refused by the authorize hook.

### Reserved test domains

`.test`, `.localhost`, `.local`, `.example`, and `.invalid` are reserved by RFC
6761/2606 and can never be publicly registered — so there is nothing to hijack
and they are verified automatically. This makes a local demo possible without
weakening the production path (the rule is a property of the domain, not an
environment flag that could be misconfigured).

---

## Demo 1 — Localhost (no domain required)

Proves mapping, verification, and host routing. Runs over plain HTTP; a
certificate is not involved (no CA will issue for a reserved TLD).

**1. Point the hostname at your machine**

```bash
sudo sh -c 'echo "127.0.0.1  help.acme.test" >> /etc/hosts'
```

**2. Start both services**

```bash
# backend
cd apps/backend && source .venv/bin/activate
uvicorn app.main:asgi --port 8000

# frontend (separate terminal)
cd apps/frontend && npm run build && npm run start
```

**3. Connect the domain**

Sign in → **Settings** → **Custom domain** → enter `help.acme.test` → **Connect**.
It verifies immediately and is labelled *Reserved test domain*.

**4. Publish an article** under **Knowledge** so there is something to see.

**5. Open the custom domain**

```
http://help.acme.test:3000
```

You should get that workspace's help centre — not the marketing homepage.
Article URLs work too: `http://help.acme.test:3000/<article-slug>`.

**What this proves:** the `Host` header is resolved to a workspace and the
correct knowledge base is served. Requests to the platform hostname are
unaffected, and disconnecting the domain immediately stops it serving.

---

## Demo 2 — A real domain (full HTTPS)

Adds the certificate step. Requires a domain you control.

**1. Tell the app what to point DNS at.** On the API service:

```
DOMAIN_CNAME_TARGET=cname.vercel-dns.com
DOMAIN_PROVIDER=manual          # or `vercel` to automate step 5
```

**2. Connect the domain** in Settings, e.g. `help.yourdomain.com`. The panel
shows two records to add.

**3. Add them at your registrar**

```
TXT    _intercom-verify.help.yourdomain.com   intercom-verify=<token>
CNAME  help.yourdomain.com                    cname.vercel-dns.com
```

**4. Click *Verify DNS*.** The backend performs a real TXT lookup. Propagation
can take a few minutes; the panel explains failures rather than just saying
"not verified".

**5. Make the certificate exist**

- `DOMAIN_PROVIDER=vercel` → done automatically on verification
- `DOMAIN_PROVIDER=manual` → add the domain once in the Vercel dashboard
  (Project → Settings → Domains)

Either way Vercel obtains a Let's Encrypt certificate and renews it every
90 days.

**6. Visit `https://help.yourdomain.com`** — the workspace's help centre,
served over HTTPS on their own domain.

### What actually happens in step 5

```
browser → https://help.yourdomain.com
platform has no certificate for that hostname yet
        ↓
ACME challenge: the CA asks the platform to prove control
        ↓
succeeds because the customer's CNAME already points at the platform
        ↓
certificate issued, installed, auto-renewed
```

---

## Self-hosting (no Vercel)

Set `DOMAIN_PROVIDER=caddy` and point Caddy's on-demand TLS at the authorize
endpoint:

```caddyfile
{
  on_demand_tls {
    ask http://api:8000/api/public/domains/authorize
  }
}

https:// {
  tls { on_demand }
  reverse_proxy frontend:3000
}
```

Caddy calls `authorize` before issuing; a `200` means the domain is verified in
our database and a certificate is fetched on the first request. No vendor API,
no dashboard — the same feature on any VPS or container host.

---

## Limitations

- A certificate cannot be issued for a reserved TLD, so the localhost demo is
  HTTP only. This is a property of the CA system, not the implementation.
- Verification checks DNS at the moment the button is pressed; a domain whose
  DNS later lapses keeps its verified flag until re-verified.
- One domain per workspace.
