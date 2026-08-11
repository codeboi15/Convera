"use client";

import { useCallback, useEffect, useState } from "react";
import { useAuth } from "@/lib/auth";
import { APP_URL } from "@/lib/config";
import type { Invite, TeamMember, WorkspaceSettings } from "@/lib/auth-types";
import type { Role } from "@/lib/types";
import { Alert, Avatar, Badge, Button, Field, Select } from "@/components/ui";

export default function SettingsPage() {
  const { authFetch, isAdmin, activeWorkspace, user } = useAuth();
  const [members, setMembers] = useState<TeamMember[]>([]);
  const [invites, setInvites] = useState<Invite[]>([]);
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<Role>("agent");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastLink, setLastLink] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [ws, setWs] = useState<WorkspaceSettings | null>(null);
  const [supportEmail, setSupportEmail] = useState("");
  const [savingEmail, setSavingEmail] = useState(false);
  const [emailSaved, setEmailSaved] = useState(false);
  const [copiedAddress, setCopiedAddress] = useState(false);

  const load = useCallback(async () => {
    try {
      setMembers(await authFetch<TeamMember[]>("/api/team/members"));
      const settings = await authFetch<WorkspaceSettings>("/api/workspace");
      setWs(settings);
      setSupportEmail(settings.support_email ?? "");
      if (isAdmin) setInvites(await authFetch<Invite[]>("/api/team/invites"));
    } catch {
      /* ignore */
    }
  }, [authFetch, isAdmin]);

  const saveSupportEmail = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSavingEmail(true);
    try {
      const updated = await authFetch<WorkspaceSettings>("/api/workspace/email", {
        method: "PATCH",
        body: { support_email: supportEmail || null },
      });
      setWs(updated);
      setEmailSaved(true);
      setTimeout(() => setEmailSaved(false), 2000);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save the address.");
    } finally {
      setSavingEmail(false);
    }
  };

  useEffect(() => {
    load();
  }, [load]);

  const invite = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const created = await authFetch<Invite>("/api/team/invites", {
        method: "POST",
        body: { email, role },
      });
      setLastLink(created.invite_url ?? null);
      setEmail("");
      load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not send the invite.");
    } finally {
      setBusy(false);
    }
  };

  const changeRole = async (userId: string, next: Role) => {
    try {
      await authFetch(`/api/team/members/${userId}`, {
        method: "PATCH",
        body: { role: next },
      });
      load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not update the role.");
    }
  };

  const remove = async (userId: string) => {
    try {
      await authFetch(`/api/team/members/${userId}`, { method: "DELETE" });
      load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not remove the member.");
    }
  };

  const widgetSnippet = `<script
  src="${APP_URL}/widget.js"
  data-workspace="${activeWorkspace?.slug ?? ""}"
  async
></script>`;

  return (
    <div className="scroll-thin h-full overflow-y-auto">
      <div className="mx-auto max-w-3xl space-y-6 px-6 py-8">
        <div>
          <h1 className="text-[26px] font-bold tracking-tight">Settings</h1>
          <p className="mt-1 text-sm text-neutral-600">
            Manage your team and install the chat widget on your site.
          </p>
        </div>

        {error && <Alert>{error}</Alert>}

        {/* Widget install */}
        <section className="card p-6">
          <h2 className="font-semibold tracking-tight">Install the chat widget</h2>
          <p className="mt-1 text-sm text-neutral-600">
            Paste this just before the closing{" "}
            <code className="rounded bg-neutral-100 px-1 py-0.5 text-xs">
              &lt;/body&gt;
            </code>{" "}
            tag on any website.
          </p>
          <pre className="mt-3.5 overflow-x-auto rounded-lg bg-neutral-900 p-4 text-xs leading-relaxed text-neutral-100">
            {widgetSnippet}
          </pre>
          <div className="mt-3.5 flex flex-wrap gap-2">
            <Button
              variant="secondary"
              size="sm"
              onClick={() => {
                navigator.clipboard?.writeText(widgetSnippet);
                setCopied(true);
                setTimeout(() => setCopied(false), 1800);
              }}
            >
              {copied ? "Copied!" : "Copy snippet"}
            </Button>
            <a
              href={`/demo?workspace=${activeWorkspace?.slug ?? ""}`}
              target="_blank"
              rel="noreferrer"
            >
              <Button variant="ghost" size="sm">
                Open demo page ↗
              </Button>
            </a>
          </div>
        </section>

        {/* Email channel */}
        <section className="card p-6">
          <h2 className="font-semibold tracking-tight">Connect your email</h2>
          <p className="mt-1 text-sm text-neutral-600">
            Every workspace gets its own address. Email sent here becomes a
            conversation in this inbox.
          </p>

          <div className="mt-4 rounded-lg border border-neutral-200 bg-neutral-50 p-4">
            <p className="text-xs font-semibold uppercase tracking-wide text-neutral-500">
              Your inbound address
            </p>
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <code className="flex-1 break-all rounded-md border border-neutral-200 bg-white px-3 py-2 text-sm">
                {ws?.inbound_address ?? "…"}
              </code>
              <Button
                variant="secondary"
                size="sm"
                onClick={() => {
                  if (!ws) return;
                  navigator.clipboard?.writeText(ws.inbound_address);
                  setCopiedAddress(true);
                  setTimeout(() => setCopiedAddress(false), 1800);
                }}
              >
                {copiedAddress ? "Copied!" : "Copy"}
              </Button>
            </div>
          </div>

          <ol className="mt-4 space-y-2 text-sm text-neutral-600">
            <li className="flex gap-2.5">
              <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-brand-50 text-[11px] font-bold text-brand-700">
                1
              </span>
              <span>
                In your mail provider (Gmail, Outlook, Zoho), forward{" "}
                <strong>support@yourcompany.com</strong> to the address above.
              </span>
            </li>
            <li className="flex gap-2.5">
              <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-brand-50 text-[11px] font-bold text-brand-700">
                2
              </span>
              <span>
                Add that same address below so replies show your branded address
                in <code className="rounded bg-neutral-100 px-1">Reply-To</code>.
              </span>
            </li>
          </ol>

          {isAdmin && (
            <form
              onSubmit={saveSupportEmail}
              className="mt-4 flex flex-wrap items-end gap-3"
            >
              <div className="min-w-[240px] flex-1">
                <Field
                  label="Your support address"
                  type="email"
                  value={supportEmail}
                  onChange={(e) => setSupportEmail(e.target.value)}
                  placeholder="support@yourcompany.com"
                  hint="Optional — used as Reply-To on outgoing replies."
                />
              </div>
              <Button type="submit" loading={savingEmail}>
                {emailSaved ? "Saved!" : "Save"}
              </Button>
            </form>
          )}
        </section>

        {/* Invite */}
        {isAdmin && (
          <section className="card p-6">
            <h2 className="font-semibold tracking-tight">Invite a teammate</h2>
            <p className="mt-1 text-sm text-neutral-600">
              Admins manage the workspace; agents handle conversations.
            </p>
            <form onSubmit={invite} className="mt-4 flex flex-wrap items-end gap-3">
              <div className="min-w-[220px] flex-1">
                <Field
                  label="Email address"
                  type="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="teammate@company.com"
                />
              </div>
              <Select
                label="Role"
                value={role}
                onChange={(e) => setRole(e.target.value as Role)}
                className="!py-2.5"
              >
                <option value="agent">Agent</option>
                <option value="admin">Admin</option>
              </Select>
              <Button type="submit" loading={busy}>
                Send invite
              </Button>
            </form>

            {lastLink && (
              <div className="mt-3">
                <Alert tone="success">
                  Invite created. Share this link:
                  <code className="mt-1 block break-all text-xs">{lastLink}</code>
                </Alert>
              </div>
            )}

            {invites.filter((i) => !i.accepted).length > 0 && (
              <div className="mt-4">
                <p className="text-sm font-medium text-neutral-700">
                  Pending invites
                </p>
                <ul className="mt-2 space-y-1.5">
                  {invites
                    .filter((i) => !i.accepted)
                    .map((i) => (
                      <li
                        key={i.id}
                        className="flex items-center justify-between gap-2 rounded-lg border border-neutral-200 bg-neutral-50/60 px-3 py-2 text-sm"
                      >
                        <span className="truncate">{i.email}</span>
                        <span className="flex shrink-0 items-center gap-2">
                          <Badge>{i.role}</Badge>
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={async () => {
                              await authFetch(`/api/team/invites/${i.id}`, {
                                method: "DELETE",
                              });
                              load();
                            }}
                            className="!text-neutral-500 hover:!text-red-600"
                          >
                            Revoke
                          </Button>
                        </span>
                      </li>
                    ))}
                </ul>
              </div>
            )}
          </section>
        )}

        {/* Members */}
        <section className="card p-6">
          <div className="flex items-baseline justify-between">
            <h2 className="font-semibold tracking-tight">Team members</h2>
            <span className="text-xs text-neutral-500">
              {members.length} {members.length === 1 ? "member" : "members"}
            </span>
          </div>
          <ul className="mt-2 divide-y divide-neutral-100">
            {members.map((m) => (
              <li key={m.user_id} className="flex items-center gap-3 py-3">
                <Avatar name={m.name || m.email} size={34} />
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm font-medium">
                    {m.name || m.email.split("@")[0]}
                    {m.user_id === user?.id && (
                      <span className="ml-1.5 text-xs font-normal text-neutral-400">
                        you
                      </span>
                    )}
                  </span>
                  <span className="block truncate text-xs text-neutral-500">
                    {m.email}
                  </span>
                </span>
                {isAdmin ? (
                  <>
                    <Select
                      value={m.role}
                      onChange={(e) => changeRole(m.user_id, e.target.value as Role)}
                      className="!py-1.5 text-xs"
                    >
                      <option value="agent">Agent</option>
                      <option value="admin">Admin</option>
                    </Select>
                    {m.user_id !== user?.id && (
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => remove(m.user_id)}
                        className="!text-neutral-500 hover:!text-red-600"
                      >
                        Remove
                      </Button>
                    )}
                  </>
                ) : (
                  <Badge tone={m.role === "admin" ? "brand" : "neutral"}>
                    {m.role}
                  </Badge>
                )}
              </li>
            ))}
          </ul>
        </section>
      </div>
    </div>
  );
}
