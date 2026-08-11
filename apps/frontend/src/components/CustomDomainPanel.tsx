"use client";

import { useCallback, useEffect, useState } from "react";
import { useAuth } from "@/lib/auth";
import { Alert, Badge, Button, Field } from "@/components/ui";

interface DomainStatus {
  domain?: string | null;
  verified: boolean;
  verified_at?: string | null;
  ssl_status: string;
  provider: string;
  dns_txt_name?: string | null;
  dns_txt_value?: string | null;
  dns_cname_name?: string | null;
  dns_cname_target?: string | null;
  public_url?: string | null;
  detail?: string | null;
  auto_verified: boolean;
}

/** One DNS row with a copy button — the records people must add verbatim. */
function DnsRow({
  type,
  name,
  value,
}: {
  type: string;
  name: string;
  value: string;
}) {
  const [copied, setCopied] = useState(false);
  return (
    <div className="flex flex-wrap items-center gap-2 rounded-lg border border-neutral-200 bg-white px-3 py-2">
      <Badge tone="outline">{type}</Badge>
      <code className="min-w-0 flex-1 break-all text-xs">
        <span className="text-neutral-500">{name}</span>
        <span className="mx-1.5 text-neutral-300">→</span>
        <span className="font-medium">{value}</span>
      </code>
      <Button
        variant="ghost"
        size="sm"
        onClick={() => {
          navigator.clipboard?.writeText(value);
          setCopied(true);
          setTimeout(() => setCopied(false), 1600);
        }}
      >
        {copied ? "Copied" : "Copy"}
      </Button>
    </div>
  );
}

export default function CustomDomainPanel() {
  const { authFetch, isAdmin } = useAuth();
  const [status, setStatus] = useState<DomainStatus | null>(null);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setStatus(await authFetch<DomainStatus>("/api/domains"));
    } catch {
      /* non-admins simply don't see this panel */
    }
  }, [authFetch]);

  useEffect(() => {
    if (isAdmin) load();
  }, [isAdmin, load]);

  if (!isAdmin) return null;

  const run = async (fn: () => Promise<DomainStatus | void>) => {
    setError(null);
    setBusy(true);
    try {
      const result = await fn();
      if (result) setStatus(result);
      else await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong.");
    } finally {
      setBusy(false);
    }
  };

  const connect = () =>
    run(() =>
      authFetch<DomainStatus>("/api/domains", {
        method: "POST",
        body: { domain: input },
      }),
    );

  const verify = () =>
    run(() => authFetch<DomainStatus>("/api/domains/verify", { method: "POST" }));

  const refreshSsl = () =>
    run(() =>
      authFetch<DomainStatus>("/api/domains/refresh-ssl", { method: "POST" }),
    );

  const disconnect = () =>
    run(async () => {
      await authFetch("/api/domains", { method: "DELETE" });
      setInput("");
    });

  const sslTone =
    status?.ssl_status === "active"
      ? "green"
      : status?.ssl_status === "error"
        ? "amber"
        : "neutral";

  return (
    <section className="card p-6">
      <h2 className="font-semibold tracking-tight">Custom domain</h2>
      <p className="mt-1 text-sm text-neutral-600">
        Serve your help centre from your own domain, like{" "}
        <code className="rounded bg-neutral-100 px-1 py-0.5 text-xs">
          help.yourcompany.com
        </code>
        .
      </p>

      {error && (
        <div className="mt-3">
          <Alert>{error}</Alert>
        </div>
      )}

      {!status?.domain ? (
        <div className="mt-4 flex flex-wrap items-end gap-3">
          <div className="min-w-[240px] flex-1">
            <Field
              label="Domain"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="help.yourcompany.com"
              hint="A subdomain you control. Use a .test domain to try it locally."
            />
          </div>
          <Button loading={busy} onClick={connect} disabled={!input.trim()}>
            Connect
          </Button>
        </div>
      ) : (
        <div className="mt-4 space-y-4">
          <div className="flex flex-wrap items-center gap-2">
            <code className="rounded-md border border-neutral-200 bg-neutral-50 px-2.5 py-1.5 text-sm font-medium">
              {status.domain}
            </code>
            <Badge tone={status.verified ? "green" : "amber"}>
              {status.verified ? "verified" : "pending verification"}
            </Badge>
            {status.verified && (
              <Badge tone={sslTone}>SSL: {status.ssl_status}</Badge>
            )}
            <Badge tone="outline">provider: {status.provider}</Badge>
          </div>

          {status.detail && (
            <p className="text-sm text-neutral-600">{status.detail}</p>
          )}

          {status.auto_verified && (
            <Alert tone="info">
              Reserved test domain — verified automatically. Add{" "}
              <code className="text-xs">127.0.0.1 {status.domain}</code> to your
              hosts file to browse it locally.
            </Alert>
          )}

          {!status.verified && status.dns_txt_name && (
            <div className="space-y-2">
              <p className="text-xs font-semibold uppercase tracking-wide text-neutral-500">
                1. Add these DNS records at your registrar
              </p>
              <DnsRow
                type="TXT"
                name={status.dns_txt_name}
                value={status.dns_txt_value ?? ""}
              />
              <DnsRow
                type="CNAME"
                name={status.dns_cname_name ?? ""}
                value={status.dns_cname_target ?? ""}
              />
              <p className="text-xs font-semibold uppercase tracking-wide text-neutral-500">
                2. Then verify
              </p>
              <p className="text-xs text-neutral-500">
                DNS changes can take a few minutes to propagate.
              </p>
            </div>
          )}

          {status.verified && status.public_url && (
            <p className="text-sm">
              Live at{" "}
              <a
                href={status.public_url}
                target="_blank"
                rel="noreferrer"
                className="font-medium text-brand hover:underline"
              >
                {status.public_url} ↗
              </a>
            </p>
          )}

          <div className="flex flex-wrap gap-2">
            {!status.verified && (
              <Button loading={busy} onClick={verify}>
                Verify DNS
              </Button>
            )}
            {status.verified && status.ssl_status !== "active" && (
              <Button variant="secondary" loading={busy} onClick={refreshSsl}>
                Check SSL status
              </Button>
            )}
            <Button variant="danger" size="sm" onClick={disconnect}>
              Disconnect
            </Button>
          </div>
        </div>
      )}
    </section>
  );
}
