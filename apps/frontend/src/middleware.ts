import { NextResponse, type NextRequest } from "next/server";
import { API_URL } from "@/lib/config";

/**
 * Serves a workspace's public knowledge base on its own custom domain.
 *
 * A request arriving on help.acme.com is rewritten to /kb/<slug> so the exact
 * same pages back both the platform URL and the customer's branded domain —
 * there is no second implementation to keep in sync.
 *
 * Only requests whose Host is *not* one of our own hostnames are considered,
 * so normal dashboard traffic is untouched.
 */

/** Hostnames that belong to the platform itself. */
function isPlatformHost(host: string): boolean {
  const appHost = (process.env.NEXT_PUBLIC_APP_URL || "")
    .replace(/^https?:\/\//, "")
    .replace(/\/.*$/, "")
    .toLowerCase();

  return (
    host === appHost ||
    host === "localhost" ||
    host.startsWith("localhost:") ||
    host.startsWith("127.0.0.1") ||
    host.endsWith(".vercel.app")
  );
}

/** Ask the API which workspace (if any) owns this hostname. */
async function resolveWorkspace(host: string): Promise<string | null> {
  try {
    const res = await fetch(
      `${API_URL}/api/public/domains/lookup?domain=${encodeURIComponent(host)}`,
      { headers: { accept: "application/json" }, cache: "no-store" },
    );
    if (!res.ok) return null;
    const data = (await res.json()) as { workspace_slug?: string };
    return data.workspace_slug ?? null;
  } catch {
    return null;
  }
}

export async function middleware(request: NextRequest) {
  const host = (request.headers.get("host") || "").toLowerCase();
  if (!host || isPlatformHost(host)) return NextResponse.next();

  const slug = await resolveWorkspace(host);
  if (!slug) return NextResponse.next();

  // Map the custom domain onto the existing knowledge-base routes:
  //   /                  → /kb/<slug>
  //   /<article-slug>     → /kb/<slug>/<article-slug>
  const path = request.nextUrl.pathname;
  const url = request.nextUrl.clone();
  url.pathname = path === "/" ? `/kb/${slug}` : `/kb/${slug}${path}`;
  return NextResponse.rewrite(url);
}

export const config = {
  // Skip Next internals, the API proxy, and static files — only page requests
  // can be custom-domain traffic.
  matcher: ["/((?!_next/|api/|widget.js|favicon.ico|.*\\..*).*)"],
};
