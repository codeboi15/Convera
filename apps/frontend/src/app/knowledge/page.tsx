"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useAuth } from "@/lib/auth";
import { APP_URL } from "@/lib/config";
import type {
  ArticleStatus,
  KBArticle,
  KBCategory,
} from "@/lib/types";
import {
  Alert,
  Badge,
  Button,
  EmptyState,
  Field,
  Select,
  Spinner,
} from "@/components/ui";
import RichTextEditor from "@/components/RichTextEditor";

type Draft = {
  title: string;
  body_html: string;
  category_id: string;
  status: ArticleStatus;
};

const EMPTY_DRAFT: Draft = {
  title: "",
  body_html: "",
  category_id: "",
  status: "draft",
};

export default function KnowledgePage() {
  const { authFetch, activeWorkspace } = useAuth();

  const [articles, setArticles] = useState<KBArticle[]>([]);
  const [categories, setCategories] = useState<KBCategory[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [draft, setDraft] = useState<Draft>(EMPTY_DRAFT);
  const [dirty, setDirty] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [filter, setFilter] = useState<"all" | ArticleStatus>("all");
  const [newCategory, setNewCategory] = useState("");

  const load = useCallback(async () => {
    try {
      const [a, c] = await Promise.all([
        authFetch<KBArticle[]>("/api/kb/articles"),
        authFetch<KBCategory[]>("/api/kb/categories"),
      ]);
      setArticles(a);
      setCategories(c);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load articles.");
    } finally {
      setLoading(false);
    }
  }, [authFetch]);

  useEffect(() => {
    load();
  }, [load]);

  const selectArticle = (article: KBArticle) => {
    setSelectedId(article.id);
    setDraft({
      title: article.title,
      body_html: article.body_html,
      category_id: article.category_id ?? "",
      status: article.status,
    });
    setDirty(false);
    setNotice(null);
  };

  const startNew = () => {
    setSelectedId(null);
    setDraft(EMPTY_DRAFT);
    setDirty(false);
    setNotice(null);
  };

  const update = (patch: Partial<Draft>) => {
    setDraft((d) => ({ ...d, ...patch }));
    setDirty(true);
  };

  /** Save the draft, optionally overriding status (used by Publish). */
  const save = async (statusOverride?: ArticleStatus) => {
    if (!draft.title.trim()) {
      setError("Give the article a title first.");
      return;
    }
    setError(null);
    setSaving(true);
    const body = {
      title: draft.title,
      body_html: draft.body_html,
      category_id: draft.category_id || null,
      status: statusOverride ?? draft.status,
    };
    try {
      const saved = selectedId
        ? await authFetch<KBArticle>(`/api/kb/articles/${selectedId}`, {
            method: "PATCH",
            body,
          })
        : await authFetch<KBArticle>("/api/kb/articles", {
            method: "POST",
            body,
          });
      setSelectedId(saved.id);
      setDraft({
        title: saved.title,
        body_html: saved.body_html,
        category_id: saved.category_id ?? "",
        status: saved.status,
      });
      setDirty(false);
      setNotice(
        saved.status === "published" ? "Published." : "Saved as draft.",
      );
      setTimeout(() => setNotice(null), 2500);
      load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save.");
    } finally {
      setSaving(false);
    }
  };

  const remove = async () => {
    if (!selectedId) return;
    try {
      await authFetch(`/api/kb/articles/${selectedId}`, { method: "DELETE" });
      startNew();
      load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not delete.");
    }
  };

  const addCategory = async () => {
    const name = newCategory.trim();
    if (!name) return;
    try {
      await authFetch("/api/kb/categories", { method: "POST", body: { name } });
      setNewCategory("");
      load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not add category.");
    }
  };

  const visible = useMemo(
    () => (filter === "all" ? articles : articles.filter((a) => a.status === filter)),
    [articles, filter],
  );

  const publicUrl = `${APP_URL}/kb/${activeWorkspace?.slug ?? ""}`;

  return (
    <div className="flex h-full">
      {/* ── Article list ─────────────────────────────────────────── */}
      <div className="flex w-[300px] shrink-0 flex-col border-r border-neutral-200 bg-white">
        <div className="flex items-center justify-between px-4 pb-2 pt-3.5">
          <h1 className="text-[17px] font-bold tracking-tight">Knowledge</h1>
          <Button size="sm" onClick={startNew}>
            New
          </Button>
        </div>

        <div className="flex items-center gap-1 border-b border-neutral-200 px-3 pb-2.5">
          {(["all", "published", "draft"] as const).map((f) => (
            <button
              key={f}
              type="button"
              onClick={() => setFilter(f)}
              className={`rounded-md px-2 py-1 text-xs font-medium capitalize transition ${
                filter === f
                  ? "bg-neutral-900 text-white"
                  : "text-neutral-600 hover:bg-neutral-100"
              }`}
            >
              {f}
            </button>
          ))}
        </div>

        <div className="scroll-thin flex-1 overflow-y-auto">
          {loading ? (
            <div className="space-y-3 p-4">
              {[0, 1, 2].map((i) => (
                <div key={i} className="skeleton h-10 rounded" />
              ))}
            </div>
          ) : visible.length === 0 ? (
            <EmptyState
              title="No articles yet"
              description="Write your first help article to power the public help centre and widget suggestions."
            />
          ) : (
            visible.map((a) => (
              <button
                key={a.id}
                type="button"
                onClick={() => selectArticle(a)}
                className={`relative w-full border-b border-neutral-100 px-4 py-3 text-left transition ${
                  selectedId === a.id ? "bg-brand-50/60" : "hover:bg-neutral-50"
                }`}
              >
                {selectedId === a.id && (
                  <span className="absolute inset-y-0 left-0 w-0.5 bg-brand" />
                )}
                <p className="truncate text-sm font-semibold">{a.title}</p>
                <span className="mt-1.5 flex items-center gap-1.5">
                  <Badge tone={a.status === "published" ? "green" : "neutral"}>
                    {a.status}
                  </Badge>
                  {a.category_name && <Badge tone="outline">{a.category_name}</Badge>}
                </span>
              </button>
            ))
          )}
        </div>

        {/* Categories */}
        <div className="border-t border-neutral-200 p-3">
          <p className="mb-1.5 text-[11px] font-semibold uppercase tracking-wide text-neutral-500">
            Categories
          </p>
          <div className="mb-2 flex flex-wrap gap-1">
            {categories.length === 0 && (
              <span className="text-xs text-neutral-400">None yet</span>
            )}
            {categories.map((c) => (
              <Badge key={c.id} tone="outline">
                {c.name} · {c.article_count}
              </Badge>
            ))}
          </div>
          <div className="flex gap-1.5">
            <input
              value={newCategory}
              onChange={(e) => setNewCategory(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && addCategory()}
              placeholder="Add category"
              className="focus-ring min-w-0 flex-1 rounded-lg border border-neutral-300 px-2 py-1.5 text-xs"
            />
            <Button variant="secondary" size="sm" onClick={addCategory}>
              Add
            </Button>
          </div>
        </div>
      </div>

      {/* ── Editor ───────────────────────────────────────────────── */}
      <div className="scroll-thin min-w-0 flex-1 overflow-y-auto bg-neutral-50">
        <div className="mx-auto max-w-3xl px-6 py-6">
          <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
            <div>
              <h2 className="text-lg font-bold tracking-tight">
                {selectedId ? "Edit article" : "New article"}
              </h2>
              <p className="mt-0.5 text-xs text-neutral-500">
                Published articles appear on your{" "}
                <a
                  href={publicUrl}
                  target="_blank"
                  rel="noreferrer"
                  className="font-medium text-brand hover:underline"
                >
                  public help centre ↗
                </a>{" "}
                and are suggested in the chat widget.
              </p>
            </div>
            <div className="flex items-center gap-2">
              {selectedId && (
                <Button variant="danger" size="sm" onClick={remove}>
                  Delete
                </Button>
              )}
              <Button variant="secondary" size="sm" onClick={() => save("draft")}>
                Save draft
              </Button>
              <Button
                size="sm"
                loading={saving}
                onClick={() => save("published")}
              >
                Publish
              </Button>
            </div>
          </div>

          {error && (
            <div className="mb-3">
              <Alert>{error}</Alert>
            </div>
          )}
          {notice && (
            <div className="mb-3">
              <Alert tone="success">{notice}</Alert>
            </div>
          )}

          <div className="space-y-4">
            <Field
              label="Title"
              value={draft.title}
              onChange={(e) => update({ title: e.target.value })}
              placeholder="How to request a refund"
            />

            <div className="flex flex-wrap items-end gap-3">
              <Select
                label="Category"
                value={draft.category_id}
                onChange={(e) => update({ category_id: e.target.value })}
              >
                <option value="">Uncategorized</option>
                {categories.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </Select>
              <span className="pb-2 text-xs text-neutral-500">
                Status:{" "}
                <Badge tone={draft.status === "published" ? "green" : "neutral"}>
                  {draft.status}
                </Badge>
                {dirty && (
                  <span className="ml-2 text-amber-600">unsaved changes</span>
                )}
              </span>
            </div>

            <div>
              <span className="mb-1.5 block text-sm font-medium text-neutral-800">
                Content
              </span>
              <RichTextEditor
                value={draft.body_html}
                onChange={(html) => update({ body_html: html })}
              />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
