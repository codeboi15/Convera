import Link from "next/link";

export default function Home() {
  return (
    <main className="mx-auto flex min-h-screen max-w-3xl flex-col items-center justify-center gap-8 px-6 text-center">
      <div className="inline-flex items-center gap-2 rounded-md border border-brand/20 bg-brand/5 px-4 py-2 text-sm font-semibold text-brand">
        <span className="h-2 w-2 rounded-full bg-brand" />
        InterCom
      </div>
      <h1 className="text-4xl font-black leading-tight tracking-tight sm:text-6xl">
        Talk to your customers,
        <br />
        <span className="text-brand">all in one inbox.</span>
      </h1>
      <p className="max-w-xl text-lg text-neutral-600">
        Live chat, email, and a knowledge base — unified in one inbox, with AI
        summaries so your team catches up in seconds.
      </p>
      <div className="flex gap-4">
        <Link
          href="/login"
          className="rounded-md bg-brand px-6 py-3 font-semibold text-white transition hover:opacity-90"
        >
          Sign in
        </Link>
        <Link
          href="/signup"
          className="rounded-md border border-neutral-300 px-6 py-3 font-semibold transition hover:border-neutral-400"
        >
          Create workspace
        </Link>
      </div>
    </main>
  );
}
