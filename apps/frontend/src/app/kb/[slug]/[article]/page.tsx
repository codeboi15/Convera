import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { API_URL } from "@/lib/config";
import { kbBasePath } from "@/lib/kbLinks";
import type { PublicArticle } from "@/lib/types";

export const dynamic = "force-dynamic";

async function fetchArticle(
  slug: string,
  article: string,
): Promise<PublicArticle | null> {
  try {
    const res = await fetch(
      `${API_URL}/api/public/kb/${encodeURIComponent(slug)}/articles/${encodeURIComponent(article)}`,
      { cache: "no-store" },
    );
    if (!res.ok) return null;
    return (await res.json()) as PublicArticle;
  } catch {
    return null;
  }
}

export async function generateMetadata({
  params,
}: {
  params: { slug: string; article: string };
}): Promise<Metadata> {
  const article = await fetchArticle(params.slug, params.article);
  return { title: article ? article.title : "Article not found" };
}

export default async function PublicArticlePage({
  params,
}: {
  params: { slug: string; article: string };
}) {
  const article = await fetchArticle(params.slug, params.article);
  if (!article) notFound();

  // On a custom domain the index is "/", not "/kb/<slug>".
  const home = kbBasePath(params.slug) || "/";

  const published = article.published_at
    ? new Date(article.published_at).toLocaleDateString(undefined, {
        year: "numeric",
        month: "long",
        day: "numeric",
      })
    : null;

  return (
    <div className="min-h-screen bg-neutral-50">
      <header className="border-b border-neutral-200 bg-white">
        <div className="mx-auto max-w-2xl px-6 py-4">
          <Link
            href={home}
            className="inline-flex items-center gap-1.5 text-sm font-medium text-neutral-600 transition hover:text-neutral-900"
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
              <path d="m15 18-6-6 6-6" />
            </svg>
            All articles
          </Link>
        </div>
      </header>

      <main className="mx-auto max-w-2xl px-6 py-10">
        <article className="card p-8">
          {article.category_name && (
            <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-brand">
              {article.category_name}
            </p>
          )}
          <h1 className="text-3xl font-extrabold leading-tight tracking-tight">
            {article.title}
          </h1>
          {published && (
            <p className="mt-2 text-sm text-neutral-500">
              Last updated {published}
            </p>
          )}

          {/*
            Body HTML is sanitised server-side with bleach before it is ever
            stored, so scripts and event handlers cannot reach this point.
          */}
          <div
            className="kb-article mt-7"
            dangerouslySetInnerHTML={{ __html: article.body_html }}
          />
        </article>

        <p className="mt-6 text-center text-sm text-neutral-500">
          Still need help? Start a chat with our team.
        </p>
      </main>

      <footer className="border-t border-neutral-200 py-8 text-center text-xs text-neutral-500">
        Powered by InterCom
      </footer>
    </div>
  );
}
