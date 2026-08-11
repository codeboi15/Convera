import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { API_URL } from "@/lib/config";
import { kbBasePath } from "@/lib/kbLinks";
import type { PublicKnowledgeBase } from "@/lib/types";
import KnowledgeBaseBrowser from "./KnowledgeBaseBrowser";

export const dynamic = "force-dynamic";

async function fetchKnowledgeBase(
  slug: string,
): Promise<PublicKnowledgeBase | null> {
  try {
    const res = await fetch(
      `${API_URL}/api/public/kb/${encodeURIComponent(slug)}`,
      { cache: "no-store" },
    );
    if (!res.ok) return null;
    return (await res.json()) as PublicKnowledgeBase;
  } catch {
    return null;
  }
}

export async function generateMetadata({
  params,
}: {
  params: { slug: string };
}): Promise<Metadata> {
  const kb = await fetchKnowledgeBase(params.slug);
  const name = kb?.workspace_name ?? "Help centre";
  return {
    title: `${name} — Help centre`,
    description: `Answers and guides from ${name}.`,
  };
}

/**
 * Public, unauthenticated help centre. Rendered server-side so articles are
 * indexable and load without a client round-trip; search is handled by the
 * client component below.
 */
export default async function PublicKnowledgeBasePage({
  params,
}: {
  params: { slug: string };
}) {
  const kb = await fetchKnowledgeBase(params.slug);
  if (!kb) notFound();

  return (
    <KnowledgeBaseBrowser
      kb={kb}
      slug={params.slug}
      basePath={kbBasePath(params.slug)}
    />
  );
}
