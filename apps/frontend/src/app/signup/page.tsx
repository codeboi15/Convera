"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";
import { Alert, AuthShell, Button, Field } from "@/components/ui";

export default function SignupPage() {
  const router = useRouter();
  const { signup, user, loading } = useAuth();
  const [form, setForm] = useState({
    name: "",
    email: "",
    password: "",
    workspace_name: "",
  });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!loading && user) router.replace("/inbox");
  }, [loading, user, router]);

  const set = (key: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm((f) => ({ ...f, [key]: e.target.value }));

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (form.password.length < 8) {
      setError("Password must be at least 8 characters.");
      return;
    }

    setBusy(true);
    try {
      await signup({
        email: form.email,
        password: form.password,
        name: form.name || undefined,
        workspace_name: form.workspace_name,
      });
      router.push("/inbox");
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "We couldn't create your workspace.",
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <AuthShell
      title="Create your workspace"
      subtitle="Set up a shared inbox for your team in under a minute."
      footer={
        <>
          Already have an account?{" "}
          <Link href="/login" className="font-semibold text-brand hover:underline">
            Sign in
          </Link>
        </>
      }
    >
      <form onSubmit={submit} className="space-y-4">
        {error && <Alert>{error}</Alert>}
        <Field
          label="Your name"
          value={form.name}
          onChange={set("name")}
          placeholder="Alex Kim"
          autoComplete="name"
        />
        <Field
          label="Work email"
          type="email"
          required
          autoComplete="email"
          value={form.email}
          onChange={set("email")}
          placeholder="you@company.com"
        />
        <Field
          label="Password"
          type="password"
          required
          minLength={8}
          autoComplete="new-password"
          value={form.password}
          onChange={set("password")}
          placeholder="At least 8 characters"
          hint="Use 8 or more characters."
        />
        <Field
          label="Workspace name"
          required
          value={form.workspace_name}
          onChange={set("workspace_name")}
          placeholder="Acme Support"
          hint="Your customers see this name in the chat widget."
        />
        <Button type="submit" loading={busy} className="w-full">
          Create workspace
        </Button>
      </form>
    </AuthShell>
  );
}
