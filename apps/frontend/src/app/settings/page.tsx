"use client";

import { useCallback, useEffect, useState } from "react";
import { useAuth } from "@/lib/auth";
import type { Invite, TeamMember } from "@/lib/auth-types";
import type { Role } from "@/lib/types";
import { Alert, Badge, Button, Field } from "@/components/ui";

export default function SettingsPage() {
  const { authFetch, isAdmin, activeWorkspace, user } = useAuth();
  const [members, setMembers] = useState<TeamMember[]>([]);
  const [invites, setInvites] = useState<Invite[]>([]);
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<Role>("agent");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastLink, setLastLink] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setMembers(await authFetch<TeamMember[]>("/api/team/members"));
      if (isAdmin) setInvites(await authFetch<Invite[]>("/api/team/invites"));
    } catch {
      /* ignore */
    }
  }, [authFetch, isAdmin]);

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
  src="${typeof window !== "undefined" ? window.location.origin : ""}/widget.js"
  data-workspace="${activeWorkspace?.slug ?? ""}"
  async
></script>`;

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-3xl space-y-8 px-6 py-8">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Settings</h1>
          <p className="mt-1 text-sm text-neutral-600">
            Manage your team and install the chat widget.
          </p>
        </div>

        {error && <Alert>{error}</Alert>}

        {/* Widget install */}
        <section className="rounded-xl border border-neutral-200 bg-white p-5">
          <h2 className="font-semibold">Install the chat widget</h2>
          <p className="mt-1 text-sm text-neutral-600">
            Paste this before <code>&lt;/body&gt;</code> on any website.
          </p>
          <pre className="mt-3 overflow-x-auto rounded-lg bg-neutral-900 p-4 text-xs leading-relaxed text-neutral-100">
            {widgetSnippet}
          </pre>
          <div className="mt-3 flex gap-2">
            <Button
              variant="secondary"
              onClick={() => navigator.clipboard?.writeText(widgetSnippet)}
            >
              Copy snippet
            </Button>
            <a
              href={`/demo?workspace=${activeWorkspace?.slug ?? ""}`}
              target="_blank"
              rel="noreferrer"
            >
              <Button variant="ghost">Open demo page</Button>
            </a>
          </div>
        </section>

        {/* Invite */}
        {isAdmin && (
          <section className="rounded-xl border border-neutral-200 bg-white p-5">
            <h2 className="font-semibold">Invite a teammate</h2>
            <form onSubmit={invite} className="mt-3 flex flex-wrap items-end gap-3">
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
              <label className="block">
                <span className="mb-1.5 block text-sm font-medium text-neutral-700">
                  Role
                </span>
                <select
                  value={role}
                  onChange={(e) => setRole(e.target.value as Role)}
                  className="rounded-lg border border-neutral-300 px-3 py-2 text-sm outline-none focus:border-brand"
                >
                  <option value="agent">Agent</option>
                  <option value="admin">Admin</option>
                </select>
              </label>
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
                        className="flex items-center justify-between rounded-lg border border-neutral-200 px-3 py-2 text-sm"
                      >
                        <span>{i.email}</span>
                        <span className="flex items-center gap-2">
                          <Badge>{i.role}</Badge>
                          <button
                            type="button"
                            onClick={async () => {
                              await authFetch(`/api/team/invites/${i.id}`, {
                                method: "DELETE",
                              });
                              load();
                            }}
                            className="text-xs font-semibold text-neutral-500 hover:text-red-600"
                          >
                            Revoke
                          </button>
                        </span>
                      </li>
                    ))}
                </ul>
              </div>
            )}
          </section>
        )}

        {/* Members */}
        <section className="rounded-xl border border-neutral-200 bg-white p-5">
          <h2 className="font-semibold">Team members</h2>
          <ul className="mt-3 divide-y divide-neutral-100">
            {members.map((m) => (
              <li key={m.user_id} className="flex items-center gap-3 py-3">
                <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-neutral-100 text-sm font-semibold">
                  {(m.name || m.email).charAt(0).toUpperCase()}
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm font-medium">
                    {m.name || m.email}
                    {m.user_id === user?.id && (
                      <span className="ml-1.5 text-xs text-neutral-400">(you)</span>
                    )}
                  </span>
                  <span className="block truncate text-xs text-neutral-500">
                    {m.email}
                  </span>
                </span>
                {isAdmin ? (
                  <>
                    <select
                      value={m.role}
                      onChange={(e) => changeRole(m.user_id, e.target.value as Role)}
                      className="rounded-lg border border-neutral-300 px-2 py-1 text-xs outline-none focus:border-brand"
                    >
                      <option value="agent">Agent</option>
                      <option value="admin">Admin</option>
                    </select>
                    {m.user_id !== user?.id && (
                      <button
                        type="button"
                        onClick={() => remove(m.user_id)}
                        className="text-xs font-semibold text-neutral-500 hover:text-red-600"
                      >
                        Remove
                      </button>
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
