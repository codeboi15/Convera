"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";
import { Avatar, Logo, Spinner } from "@/components/ui";

const NAV = [
  {
    href: "/inbox",
    label: "Inbox",
    icon: "M22 12h-6l-2 3h-4l-2-3H2M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z",
  },
  {
    href: "/knowledge",
    label: "Knowledge",
    icon: "M4 19.5A2.5 2.5 0 0 1 6.5 17H20M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z",
  },
  {
    href: "/analytics",
    label: "Analytics",
    icon: "M3 3v18h18M18 17V9M13 17V5M8 17v-3",
  },
  {
    href: "/settings",
    label: "Settings",
    icon: "M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.6V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z",
  },
];

export default function DashboardShell({
  children,
}: {
  children: React.ReactNode;
}) {
  const { user, loading, logout, workspaces, activeWorkspace, switchWorkspace } =
    useAuth();
  const router = useRouter();
  const pathname = usePathname();
  const [wsOpen, setWsOpen] = useState(false);
  const [userOpen, setUserOpen] = useState(false);
  const wsRef = useRef<HTMLDivElement>(null);
  const userRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!loading && !user) router.replace("/login");
  }, [loading, user, router]);

  // Close menus on outside click.
  useEffect(() => {
    const onClick = (e: MouseEvent) => {
      if (wsRef.current && !wsRef.current.contains(e.target as Node))
        setWsOpen(false);
      if (userRef.current && !userRef.current.contains(e.target as Node))
        setUserOpen(false);
    };
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, []);

  if (loading) {
    return (
      <div className="flex h-screen items-center justify-center bg-neutral-50">
        <Spinner className="h-6 w-6" />
      </div>
    );
  }
  if (!user) return null;

  return (
    <div className="flex h-screen overflow-hidden bg-neutral-50">
      <aside className="flex w-[248px] shrink-0 flex-col border-r border-neutral-200 bg-white">
        {/* Workspace switcher */}
        <div ref={wsRef} className="relative p-2.5">
          <button
            type="button"
            onClick={() => setWsOpen((v) => !v)}
            className="flex w-full items-center gap-2.5 rounded-lg p-2 text-left transition hover:bg-neutral-100"
          >
            <Logo size={30} />
            <span className="min-w-0 flex-1">
              <span className="block truncate text-sm font-semibold leading-tight">
                {activeWorkspace?.name ?? "Workspace"}
              </span>
              <span className="block truncate text-xs capitalize text-neutral-500">
                {activeWorkspace?.role ?? ""}
              </span>
            </span>
            <svg
              width="14"
              height="14"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              className={`shrink-0 text-neutral-400 transition-transform ${
                wsOpen ? "rotate-180" : ""
              }`}
            >
              <path d="m6 9 6 6 6-6" />
            </svg>
          </button>

          {wsOpen && (
            <div className="absolute left-2.5 right-2.5 top-full z-30 mt-1 overflow-hidden rounded-xl border border-neutral-200 bg-white py-1 shadow-pop">
              <p className="px-3 py-1.5 text-[11px] font-semibold uppercase tracking-wide text-neutral-400">
                Workspaces
              </p>
              {workspaces.map((w) => (
                <button
                  key={w.id}
                  type="button"
                  onClick={async () => {
                    setWsOpen(false);
                    if (w.id !== activeWorkspace?.id) await switchWorkspace(w.id);
                  }}
                  className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm transition hover:bg-neutral-50"
                >
                  <Avatar name={w.name} size={22} />
                  <span className="min-w-0 flex-1 truncate">{w.name}</span>
                  {w.id === activeWorkspace?.id && (
                    <svg
                      width="14"
                      height="14"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="3"
                      className="shrink-0 text-brand"
                    >
                      <path d="m20 6-11 11-5-5" />
                    </svg>
                  )}
                </button>
              ))}
            </div>
          )}
        </div>

        <nav className="flex-1 space-y-0.5 px-2.5 py-1">
          {NAV.map((item) => {
            const active = pathname.startsWith(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm font-medium transition ${
                  active
                    ? "bg-brand-50 text-brand-700"
                    : "text-neutral-700 hover:bg-neutral-100"
                }`}
              >
                <svg
                  width="17"
                  height="17"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  className={active ? "text-brand" : "text-neutral-400"}
                >
                  <path d={item.icon} />
                </svg>
                {item.label}
              </Link>
            );
          })}
        </nav>

        {/* User menu */}
        <div ref={userRef} className="relative border-t border-neutral-200 p-2.5">
          <button
            type="button"
            onClick={() => setUserOpen((v) => !v)}
            className="flex w-full items-center gap-2.5 rounded-lg p-1.5 text-left transition hover:bg-neutral-100"
          >
            <Avatar name={user.name || user.email} size={30} />
            <span className="min-w-0 flex-1">
              <span className="block truncate text-sm font-medium leading-tight">
                {user.name || user.email.split("@")[0]}
              </span>
              <span className="block truncate text-xs text-neutral-500">
                {user.email}
              </span>
            </span>
          </button>

          {userOpen && (
            <div className="absolute bottom-full left-2.5 right-2.5 z-30 mb-1 overflow-hidden rounded-xl border border-neutral-200 bg-white py-1 shadow-pop">
              <button
                type="button"
                onClick={logout}
                className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm text-neutral-700 transition hover:bg-neutral-50"
              >
                <svg
                  width="15"
                  height="15"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9" />
                </svg>
                Sign out
              </button>
            </div>
          )}
        </div>
      </aside>

      <div className="min-w-0 flex-1 overflow-hidden">{children}</div>
    </div>
  );
}
