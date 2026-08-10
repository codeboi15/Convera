import Link from "next/link";
import { Wordmark } from "@/components/ui";

const FEATURES = [
  {
    title: "Live chat widget",
    body: "One script tag puts a real-time chat bubble on any site. Typing indicators, read receipts, and history that survives a refresh.",
    icon: "M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z",
  },
  {
    title: "Email, threaded",
    body: "Customer emails land in the same inbox. Reply from the dashboard and it arrives as a normal, correctly threaded email.",
    icon: "M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2zm18 4-10 5L2 8",
  },
  {
    title: "Unified inbox",
    body: "Chat and email side by side. Filter by channel, assignee, or status. Assign, snooze, and resolve without leaving the keyboard.",
    icon: "M22 12h-6l-2 3h-4l-2-3H2M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z",
  },
  {
    title: "Knowledge base",
    body: "Publish help articles, search them publicly, and surface the right one inside the chat widget as the customer types.",
    icon: "M4 19.5A2.5 2.5 0 0 1 6.5 17H20M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z",
  },
  {
    title: "AI summaries",
    body: "Long thread? Get what the customer wants, what's been tried, and where it stands — refreshed as the conversation moves.",
    icon: "M12 2 9.6 8.6 3 11l6.6 2.4L12 20l2.4-6.6L21 11l-6.6-2.4L12 2z",
  },
  {
    title: "Custom domains",
    body: "Serve your help centre from help.yourdomain.com with SSL handled for you.",
    icon: "M12 22c5.5 0 10-4.5 10-10S17.5 2 12 2 2 6.5 2 12s4.5 10 10 10zM2 12h20M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z",
  },
];

export default function Home() {
  return (
    <div className="min-h-screen bg-white">
      <header className="sticky top-0 z-30 border-b border-neutral-200/70 bg-white/80 backdrop-blur">
        <div className="mx-auto flex max-w-5xl items-center justify-between px-6 py-3.5">
          <Wordmark />
          <nav className="flex items-center gap-2">
            <Link
              href="/login"
              className="rounded-lg px-3.5 py-2 text-sm font-semibold text-neutral-700 transition hover:bg-neutral-100"
            >
              Sign in
            </Link>
            <Link
              href="/signup"
              className="rounded-lg bg-brand px-3.5 py-2 text-sm font-semibold text-white shadow-sm transition hover:bg-brand-700"
            >
              Get started
            </Link>
          </nav>
        </div>
      </header>

      {/* Hero */}
      <section className="relative overflow-hidden border-b border-neutral-200">
        <div
          aria-hidden
          className="pointer-events-none absolute inset-0"
          style={{
            backgroundImage:
              "radial-gradient(50rem 26rem at 50% -8%, rgba(79,70,229,.12), transparent 70%)",
          }}
        />
        <div className="relative mx-auto max-w-3xl px-6 py-24 text-center">
          <span className="inline-flex items-center gap-2 rounded-full border border-brand-200 bg-brand-50 px-3 py-1 text-xs font-semibold text-brand-700">
            <span className="h-1.5 w-1.5 rounded-full bg-brand" />
            Chat · Email · Knowledge base
          </span>
          <h1 className="mt-6 text-[44px] font-extrabold leading-[1.06] tracking-[-0.03em] sm:text-6xl">
            One inbox for every
            <br />
            customer conversation.
          </h1>
          <p className="mx-auto mt-5 max-w-xl text-lg leading-relaxed text-neutral-600">
            InterCom brings live chat and email into a single shared inbox — with a
            knowledge base and AI summaries so your team always knows the context.
          </p>
          <div className="mt-9 flex flex-wrap items-center justify-center gap-3">
            <Link
              href="/signup"
              className="rounded-lg bg-brand px-5 py-3 text-sm font-semibold text-white shadow-sm transition hover:bg-brand-700"
            >
              Create your workspace
            </Link>
            <Link
              href="/login"
              className="rounded-lg border border-neutral-300 bg-white px-5 py-3 text-sm font-semibold transition hover:bg-neutral-50"
            >
              Sign in
            </Link>
          </div>
          <p className="mt-4 text-xs text-neutral-500">
            Free to set up · No credit card required
          </p>
        </div>
      </section>

      {/* Features */}
      <section className="mx-auto max-w-5xl px-6 py-20">
        <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {FEATURES.map((f) => (
            <div
              key={f.title}
              className="card p-5 transition hover:border-neutral-300 hover:shadow-pop"
            >
              <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-brand-50 text-brand">
                <svg
                  width="18"
                  height="18"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <path d={f.icon} />
                </svg>
              </span>
              <h3 className="mt-3.5 font-semibold tracking-tight">{f.title}</h3>
              <p className="mt-1.5 text-sm leading-relaxed text-neutral-600">
                {f.body}
              </p>
            </div>
          ))}
        </div>
      </section>

      <footer className="border-t border-neutral-200">
        <div className="mx-auto flex max-w-5xl flex-wrap items-center justify-between gap-3 px-6 py-8 text-sm text-neutral-500">
          <Wordmark />
          <span>Built for the SuperProfile Member of Technical Staff assignment.</span>
        </div>
      </footer>
    </div>
  );
}
