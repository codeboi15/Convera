"use client";

import { useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { apiFetch } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { AuthResponse } from "@/lib/auth-types";
import { Alert, AuthShell, Button, Field } from "@/components/ui";

/**
 * Invite acceptance. The same endpoint handles both cases — an existing user
 * simply joins, a new user sets a password — so the form asks for a password
 * and the backend ignores it when the account already exists.
 */
export default function AcceptInvitePage() {
  const params = useParams<{ token: string }>();
  const router = useRouter();
  const { applyAuth } = useAuth();

  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const data = await apiFetch<AuthResponse>("/api/team/invites/accept", {
        method: "POST",
        body: {
          token: params.token,
          name: name || undefined,
          password: password || undefined,
        },
      });
      applyAuth(data);
      router.push("/inbox");
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "This invite could not be accepted. Ask your admin to resend it.",
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <AuthShell
      title="Join your team"
      subtitle="You've been invited to a workspace on InterCom."
      footer={
        <>
          Wrong account?{" "}
          <Link href="/login" className="font-semibold text-brand hover:underline">
            Sign in instead
          </Link>
        </>
      }
    >
      <form onSubmit={submit} className="space-y-4">
        {error && <Alert>{error}</Alert>}
        <Field
          label="Your name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Alex Kim"
          autoComplete="name"
        />
        <Field
          label="Choose a password"
          type="password"
          minLength={8}
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder="At least 8 characters"
          autoComplete="new-password"
          hint="Skip this if you already have an InterCom account."
        />
        <Button type="submit" loading={busy} className="w-full">
          Accept invite
        </Button>
      </form>
    </AuthShell>
  );
}
