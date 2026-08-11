"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { API_URL } from "@/lib/config";
import type { ArticleSummary, PublicKnowledgeBase } from "@/lib/types";

export default function KnowledgeBaseBrowser({
  kb,
  slug,
  basePath,
}: {
  kb: PublicKnowledgeBase;
  slug: string;
  /** Link prefix: "/kb/<slug>" on the platform host, "" on a custom domain. */
  basePath: string;
}) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<ArticleSummary[] | null>(null);
  const [searching, setSearching] = useState(false);

  // Debounced search against the public endpoint (FTS + fuzzy fallback).
  useEffect(() => {
    const q = query.trim();
    if (q.length < 2) {
      setResults(null);
      return;
    }
    let cancelled = false;
    setSearching(true);
    const timer = setTimeout(async () => {
      try {
        const res = await fetch(
          `${API_URL}/api/public/kb/${encodeURIComponent(slug)}/search?q=${encodeURIComponent(q)}`,
          { cache: "no-store" },
        );
        if (!cancelled) setResults(res.ok ? await res.json() : []);
      } catch {
        if (!cancelled) setResults([]);
      } finally {
        if (!cancelled) setSearching(false);
      }
    }, 220);

    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [query, slug]);

  const totalArticles = useMemo(
    () =>
      kb.categories.reduce((n, c) => n + c.articles.length, 0) +
      kb.uncategorized.length,
    [kb],
  );

  return (
    <div className="min-h-screen bg-neutral-50">
      {/* Header + search */}
      <header className="relative overflow-hidden border-b border-neutral-200 bg-white">
        <div
          aria-hidden
          className="pointer-events-none absolute inset-0"
          style={{
            backgroundImage:
              "radial-gradient(40rem 20rem at 50% -20%, rgba(79,70,229,.10), transparent 70%)",
          }}
        />
        <div className="relative mx-auto max-w-3xl px-6 py-14 text-center">
          <h1 className="text-3xl font-extrabold tracking-tight sm:text-4xl">
            {kb.workspace_name} Help Centre
          </h1>
          <p className="mt-2 text-neutral-600">
            Search {totalArticles} article{totalArticles === 1 ? "" : "s"}, or
            browse by topic below.
          </p>

          <div className="relative mx-auto mt-7 max-w-xl">
            <svg
              width="18"
              height="18"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-neutral-400"
            >
              <circle cx="11" cy="11" r="8" />
              <path d="m21 21-4.3-4.3" />
            </svg>
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search for an answer…"
              aria-label="Search help articles"
              className="focus-ring w-full rounded-xl border border-neutral-300 bg-white py-3 pl-11 pr-4 text-sm shadow-sm placeholder:text-neutral-400"
            />
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-3xl px-6 py-10">
        {/* Search results replace the browse view while a query is active */}
        {results !== null ? (
          <section>
            <p className="mb-4 text-sm text-neutral-600">
              {searching
                ? "Searching…"
                : `${results.length} result${results.length === 1 ? "" : "s"} for “${query.trim()}”`}
            </p>
            {results.length === 0 && !searching ? (
              <div className="card p-8 text-center">
                <p className="text-sm font-semibold">No matching articles</p>
                <p className="mt-1 text-sm text-neutral-500">
                  Try different words, or start a chat with our team.
                </p>
              </div>
            ) : (
              <ul className="space-y-2.5">
                {results.map((a) => (
                  <li key={a.id}>
                    <ArticleCard basePath={basePath} article={a} />
                  </li>
                ))}
              </ul>
            )}
          </section>
        ) : (
          <div className="space-y-9">
            {kb.categories.map((category) => (
              <section key={category.slug}>
                <h2 className="mb-3 text-sm font-bold uppercase tracking-wide text-neutral-500">
                  {category.name}
                </h2>
                <ul className="space-y-2.5">
                  {category.articles.map((a) => (
                    <li key={a.id}>
                      <ArticleCard basePath={basePath} article={a} />
                    </li>
                  ))}
                </ul>
              </section>
            ))}

            {kb.uncategorized.length > 0 && (
              <section>
                <h2 className="mb-3 text-sm font-bold uppercase tracking-wide text-neutral-500">
                  Other articles
                </h2>
                <ul className="space-y-2.5">
                  {kb.uncategorized.map((a) => (
                    <li key={a.id}>
                      <ArticleCard basePath={basePath} article={a} />
                    </li>
                  ))}
                </ul>
              </section>
            )}

            {totalArticles === 0 && (
              <div className="card p-10 text-center">
                <p className="text-sm font-semibold">No articles published yet</p>
                <p className="mt-1 text-sm text-neutral-500">
                  Check back soon — or reach out to the team directly.
                </p>
              </div>
            )}
          </div>
        )}
      </main>

      <footer className="border-t border-neutral-200 py-8 text-center text-xs text-neutral-500">
        Powered by InterCom
      </footer>
    </div>
  );
}

function ArticleCard({
  basePath,
  article,
}: {
  basePath: string;
  article: ArticleSummary;
}) {
  return (
    <Link
      href={`${basePath}/${article.slug}`}
      className="card block p-4 transition hover:border-neutral-300 hover:shadow-pop"
    >
      <p className="font-semibold tracking-tight">{article.title}</p>
      {article.excerpt && (
        <p className="mt-1 line-clamp-2 text-sm text-neutral-600">
          {article.excerpt}
        </p>
      )}
    </Link>
  );
}
