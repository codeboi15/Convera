"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";
import { Alert, AuthShell, Button, Field } from "@/components/ui";

export default function LoginPage() {
  const router = useRouter();
  const { login, user, loading } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!loading && user) router.replace("/inbox");
  }, [loading, user, router]);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await login(email, password);
      router.push("/inbox");
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "We couldn't sign you in. Try again.",
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <AuthShell
      title="Sign in"
      subtitle="Welcome back. Pick up where your team left off."
      footer={
        <>
          New here?{" "}
          <Link href="/signup" className="font-semibold text-brand hover:underline">
            Create a workspace
          </Link>
        </>
      }
    >
      <form onSubmit={submit} className="space-y-4">
        {error && <Alert>{error}</Alert>}
        <Field
          label="Work email"
          type="email"
          autoComplete="email"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="you@company.com"
        />
        <Field
          label="Password"
          type="password"
          autoComplete="current-password"
          required
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder="••••••••"
        />
        <Button type="submit" loading={busy} className="w-full">
          Sign in
        </Button>
      </form>
    </AuthShell>
  );
}
