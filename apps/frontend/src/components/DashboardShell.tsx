"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";

const NAV = [
  { href: "/inbox", label: "Inbox", icon: "M22 12h-6l-2 3h-4l-2-3H2M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z" },
  { href: "/knowledge", label: "Knowledge", icon: "M4 19.5A2.5 2.5 0 0 1 6.5 17H20M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" },
  { href: "/analytics", label: "Analytics", icon: "M3 3v18h18M18 17V9M13 17V5M8 17v-3" },
  { href: "/settings", label: "Settings", icon: "M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.6V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" },
];

export default function DashboardShell({ children }: { children: React.ReactNode }) {
  const { user, loading, logout, workspaces, activeWorkspace, switchWorkspace } =
    useAuth();
  const router = useRouter();
  const pathname = usePathname();
  const [menuOpen, setMenuOpen] = useState(false);

  useEffect(() => {
    if (!loading && !user) router.replace("/login");
  }, [loading, user, router]);

  if (loading) {
    return (
      <div className="flex h-screen items-center justify-center bg-neutral-50">
        <span className="h-6 w-6 animate-spin rounded-full border-2 border-neutral-300 border-t-brand" />
      </div>
    );
  }
  if (!user) return null;

  return (
    <div className="flex h-screen bg-neutral-50">
      <aside className="flex w-60 shrink-0 flex-col border-r border-neutral-200 bg-white">
        <div className="relative border-b border-neutral-200 p-3">
          <button
            type="button"
            onClick={() => setMenuOpen((v) => !v)}
            className="flex w-full items-center gap-2 rounded-lg p-2 text-left transition hover:bg-neutral-100"
          >
            <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-brand text-sm font-bold text-white">
              {(activeWorkspace?.name ?? "W").charAt(0).toUpperCase()}
            </span>
            <span className="min-w-0 flex-1">
              <span className="block truncate text-sm font-semibold">
                {activeWorkspace?.name ?? "Workspace"}
              </span>
              <span className="block truncate text-xs capitalize text-neutral-500">
                {activeWorkspace?.role ?? ""}
              </span>
            </span>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="text-neutral-400">
              <path d="m6 9 6 6 6-6" />
            </svg>
          </button>

          {menuOpen && (
            <div className="absolute left-3 right-3 top-full z-20 mt-1 overflow-hidden rounded-lg border border-neutral-200 bg-white shadow-lg">
              {workspaces.map((w) => (
                <button
                  key={w.id}
                  type="button"
                  onClick={async () => {
                    setMenuOpen(false);
                    if (w.id !== activeWorkspace?.id) await switchWorkspace(w.id);
                  }}
                  className={`flex w-full items-center justify-between px-3 py-2 text-left text-sm transition hover:bg-neutral-50 ${
                    w.id === activeWorkspace?.id ? "font-semibold text-brand" : ""
                  }`}
                >
                  <span className="truncate">{w.name}</span>
                  <span className="ml-2 shrink-0 text-xs capitalize text-neutral-400">
                    {w.role}
                  </span>
                </button>
              ))}
            </div>
          )}
        </div>

        <nav className="flex-1 space-y-0.5 p-2">
          {NAV.map((item) => {
            const active = pathname.startsWith(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm font-medium transition ${
                  active
                    ? "bg-brand/10 text-brand"
                    : "text-neutral-700 hover:bg-neutral-100"
                }`}
              >
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d={item.icon} />
                </svg>
                {item.label}
              </Link>
            );
          })}
        </nav>

        <div className="border-t border-neutral-200 p-3">
          <p className="truncate text-sm font-medium">{user.name || user.email}</p>
          <p className="truncate text-xs text-neutral-500">{user.email}</p>
          <button
            type="button"
            onClick={logout}
            className="mt-2 text-xs font-semibold text-neutral-500 transition hover:text-red-600"
          >
            Sign out
          </button>
        </div>
      </aside>

      <div className="min-w-0 flex-1 overflow-hidden">{children}</div>
    </div>
  );
}
