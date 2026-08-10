"use client";

import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode } from "react";

/* ── Brand mark ─────────────────────────────────────────────────────────── */

export function Logo({ size = 28 }: { size?: number }) {
  return (
    <span
      className="inline-flex items-center justify-center rounded-lg bg-brand text-white shadow-sm"
      style={{ width: size, height: size }}
    >
      <svg
        width={size * 0.58}
        height={size * 0.58}
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2.4"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        <path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z" />
      </svg>
    </span>
  );
}

export function Wordmark() {
  return (
    <span className="inline-flex items-center gap-2 font-bold tracking-tight">
      <Logo />
      InterCom
    </span>
  );
}

/* ── Avatar ─────────────────────────────────────────────────────────────── */

const AVATAR_COLORS = [
  "bg-rose-100 text-rose-700",
  "bg-amber-100 text-amber-700",
  "bg-emerald-100 text-emerald-700",
  "bg-sky-100 text-sky-700",
  "bg-violet-100 text-violet-700",
  "bg-fuchsia-100 text-fuchsia-700",
  "bg-teal-100 text-teal-700",
];

/** Deterministic colour so a person keeps the same avatar between renders. */
export function Avatar({
  name,
  size = 36,
}: {
  name?: string | null;
  size?: number;
}) {
  const label = (name || "?").trim();
  const initial = label.charAt(0).toUpperCase() || "?";
  let hash = 0;
  for (let i = 0; i < label.length; i++) hash = (hash * 31 + label.charCodeAt(i)) | 0;
  const color = AVATAR_COLORS[Math.abs(hash) % AVATAR_COLORS.length];

  return (
    <span
      className={`inline-flex shrink-0 items-center justify-center rounded-full font-semibold ${color}`}
      style={{ width: size, height: size, fontSize: size * 0.4 }}
      title={label}
    >
      {initial}
    </span>
  );
}

/* ── Form controls ──────────────────────────────────────────────────────── */

export function Field({
  label,
  hint,
  error,
  ...props
}: InputHTMLAttributes<HTMLInputElement> & {
  label: string;
  hint?: string;
  error?: string;
}) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-sm font-medium text-neutral-800">
        {label}
      </span>
      <input
        {...props}
        className={`focus-ring w-full rounded-lg border bg-white px-3.5 py-2.5 text-sm placeholder:text-neutral-400 disabled:bg-neutral-50 ${
          error ? "border-red-300" : "border-neutral-300"
        }`}
      />
      {error ? (
        <span className="mt-1.5 block text-xs text-red-600">{error}</span>
      ) : (
        hint && <span className="mt-1.5 block text-xs text-neutral-500">{hint}</span>
      )}
    </label>
  );
}

export function Select({
  label,
  children,
  className = "",
  ...props
}: React.SelectHTMLAttributes<HTMLSelectElement> & { label?: string }) {
  const select = (
    <select
      {...props}
      className={`focus-ring cursor-pointer rounded-lg border border-neutral-300 bg-white px-3 py-2 text-sm ${className}`}
    >
      {children}
    </select>
  );
  if (!label) return select;
  return (
    <label className="block">
      <span className="mb-1.5 block text-sm font-medium text-neutral-800">
        {label}
      </span>
      {select}
    </label>
  );
}

export function Button({
  children,
  variant = "primary",
  size = "md",
  loading,
  className = "",
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "ghost" | "danger";
  size?: "sm" | "md";
  loading?: boolean;
}) {
  const variants: Record<string, string> = {
    primary:
      "bg-brand text-white shadow-sm hover:bg-brand-700 active:bg-brand-700",
    secondary:
      "border border-neutral-300 bg-white text-neutral-800 hover:bg-neutral-50 active:bg-neutral-100",
    ghost: "text-neutral-600 hover:bg-neutral-100 hover:text-neutral-900",
    danger: "border border-red-200 bg-white text-red-600 hover:bg-red-50",
  };
  const sizes: Record<string, string> = {
    sm: "px-2.5 py-1.5 text-xs",
    md: "px-4 py-2.5 text-sm",
  };
  return (
    <button
      {...props}
      disabled={props.disabled || loading}
      className={`inline-flex select-none items-center justify-center gap-2 whitespace-nowrap rounded-lg font-semibold transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${variants[variant]} ${sizes[size]} ${className}`}
    >
      {loading && (
        <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-current border-t-transparent" />
      )}
      {children}
    </button>
  );
}

export function IconButton({
  children,
  label,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { label: string }) {
  return (
    <button
      {...props}
      aria-label={label}
      title={label}
      className="inline-flex h-8 w-8 items-center justify-center rounded-lg text-neutral-500 transition hover:bg-neutral-100 hover:text-neutral-900"
    >
      {children}
    </button>
  );
}

/* ── Feedback ───────────────────────────────────────────────────────────── */

export function Alert({
  children,
  tone = "error",
}: {
  children: ReactNode;
  tone?: "error" | "success" | "info";
}) {
  const tones: Record<string, string> = {
    error: "border-red-200 bg-red-50 text-red-800",
    success: "border-emerald-200 bg-emerald-50 text-emerald-800",
    info: "border-sky-200 bg-sky-50 text-sky-800",
  };
  return (
    <div className={`rounded-lg border px-3.5 py-2.5 text-sm ${tones[tone]}`}>
      {children}
    </div>
  );
}

export function Badge({
  children,
  tone = "neutral",
}: {
  children: ReactNode;
  tone?: "neutral" | "brand" | "green" | "amber" | "outline";
}) {
  const tones: Record<string, string> = {
    neutral: "bg-neutral-100 text-neutral-600",
    brand: "bg-brand-50 text-brand-700",
    green: "bg-emerald-50 text-emerald-700",
    amber: "bg-amber-50 text-amber-700",
    outline: "border border-neutral-200 text-neutral-600",
  };
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[11px] font-medium capitalize leading-4 ${tones[tone]}`}
    >
      {children}
    </span>
  );
}

export function EmptyState({
  icon,
  title,
  description,
  action,
}: {
  icon?: ReactNode;
  title: string;
  description?: string;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center px-6 py-14 text-center">
      {icon && (
        <span className="mb-3 flex h-11 w-11 items-center justify-center rounded-xl bg-neutral-100 text-neutral-400">
          {icon}
        </span>
      )}
      <p className="text-sm font-semibold text-neutral-800">{title}</p>
      {description && (
        <p className="mt-1 max-w-xs text-sm text-neutral-500">{description}</p>
      )}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export function Spinner({ className = "" }: { className?: string }) {
  return (
    <span
      className={`inline-block animate-spin rounded-full border-2 border-neutral-300 border-t-brand ${className}`}
    />
  );
}

/* ── Auth layout ────────────────────────────────────────────────────────── */

export function AuthShell({
  title,
  subtitle,
  children,
  footer,
}: {
  title: string;
  subtitle?: string;
  children: ReactNode;
  footer?: ReactNode;
}) {
  return (
    <main className="relative flex min-h-screen items-center justify-center overflow-hidden bg-neutral-50 px-4 py-12">
      {/* soft background wash */}
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 opacity-70"
        style={{
          backgroundImage:
            "radial-gradient(60rem 30rem at 50% -10%, rgba(79,70,229,.10), transparent 70%)",
        }}
      />
      <div className="relative w-full max-w-[400px]">
        <div className="mb-7 flex justify-center">
          <Wordmark />
        </div>
        <div className="card p-7">
          <h1 className="text-[22px] font-bold tracking-tight">{title}</h1>
          {subtitle && (
            <p className="mt-1.5 text-sm leading-relaxed text-neutral-600">
              {subtitle}
            </p>
          )}
          <div className="mt-6">{children}</div>
        </div>
        {footer && (
          <p className="mt-5 text-center text-sm text-neutral-600">{footer}</p>
        )}
      </div>
    </main>
  );
}
