import type { Metadata } from "next";
import WidgetEmbed from "./WidgetEmbed";

export const metadata: Metadata = {
  title: "Widget demo — InterCom",
  description: "A sample website with the InterCom chat widget installed.",
};

/**
 * Stand-in "customer website" that installs the widget exactly the way a real
 * site would — one script tag. Used to demo end-to-end realtime delivery.
 */
export default function DemoPage({
  searchParams,
}: {
  searchParams: { workspace?: string };
}) {
  const workspace = searchParams.workspace ?? "";

  return (
    <main className="min-h-screen bg-white">
      <header className="border-b border-neutral-200">
        <div className="mx-auto flex max-w-4xl items-center justify-between px-6 py-4">
          <span className="text-lg font-bold tracking-tight">Northwind Coffee</span>
          <nav className="hidden gap-6 text-sm text-neutral-600 sm:flex">
            <span>Shop</span>
            <span>About</span>
            <span>Contact</span>
          </nav>
        </div>
      </header>

      <section className="mx-auto max-w-4xl px-6 py-20">
        <p className="text-sm font-semibold uppercase tracking-widest text-brand">
          Demo site
        </p>
        <h1 className="mt-3 text-4xl font-black tracking-tight sm:text-5xl">
          A sample website with live chat installed.
        </h1>
        <p className="mt-4 max-w-2xl text-lg text-neutral-600">
          This page is not part of the InterCom dashboard. It exists to prove the
          widget can be dropped onto any website with a single script tag. Click
          the bubble in the bottom-right corner and send a message — it appears in
          the agent inbox instantly.
        </p>

        {!workspace && (
          <div className="mt-8 rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800">
            Add your workspace slug to the URL to load the widget, e.g.{" "}
            <code className="rounded bg-amber-100 px-1.5 py-0.5">
              /demo?workspace=your-workspace-slug
            </code>
          </div>
        )}

        <div className="mt-10 rounded-lg border border-neutral-200 bg-neutral-50 p-5">
          <p className="text-sm font-semibold">Installation</p>
          <pre className="mt-3 overflow-x-auto rounded bg-neutral-900 p-4 text-xs leading-relaxed text-neutral-100">
{`<script
  src="${"{your-app-url}"}/widget.js"
  data-workspace="${workspace || "your-workspace-slug"}"
  async
></script>`}
          </pre>
        </div>
      </section>

      {workspace ? <WidgetEmbed workspace={workspace} /> : null}
    </main>
  );
}
