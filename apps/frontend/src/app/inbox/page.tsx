"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useAuth } from "@/lib/auth";
import { useAgentSocket } from "@/lib/useAgentSocket";
import type {
  Conversation,
  ConversationDetail,
  ConversationList,
  Message,
} from "@/lib/types";
import type { TeamMember } from "@/lib/auth-types";
import {
  Avatar,
  Badge,
  Button,
  EmptyState,
  Select,
} from "@/components/ui";

type StatusFilter = "open" | "snoozed" | "resolved" | "all";
type ChannelFilter = "all" | "chat" | "email";

const STATUS_TABS: StatusFilter[] = ["open", "snoozed", "resolved", "all"];
const CHANNEL_TABS: ChannelFilter[] = ["all", "chat", "email"];

function timeAgo(iso?: string | null): string {
  if (!iso) return "";
  const mins = Math.floor((Date.now() - new Date(iso).getTime()) / 60000);
  if (mins < 1) return "now";
  if (mins < 60) return `${mins}m`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h`;
  const days = Math.floor(hrs / 24);
  return days < 7 ? `${days}d` : `${Math.floor(days / 7)}w`;
}

function dayLabel(iso: string): string {
  const d = new Date(iso);
  const today = new Date();
  const yest = new Date();
  yest.setDate(today.getDate() - 1);
  if (d.toDateString() === today.toDateString()) return "Today";
  if (d.toDateString() === yest.toDateString()) return "Yesterday";
  return d.toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    year: d.getFullYear() === today.getFullYear() ? undefined : "numeric",
  });
}

function displayName(c: { name?: string | null; email?: string | null }) {
  return c.name || c.email || "Anonymous visitor";
}

export default function InboxPage() {
  const { authFetch, accessToken, user } = useAuth();
  const { socket, connected } = useAgentSocket(accessToken);

  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<ConversationDetail | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [members, setMembers] = useState<TeamMember[]>([]);
  const [draft, setDraft] = useState("");
  const [status, setStatus] = useState<StatusFilter>("open");
  const [channel, setChannel] = useState<ChannelFilter>("all");
  const [mineOnly, setMineOnly] = useState(false);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [threadLoading, setThreadLoading] = useState(false);
  const [contactTyping, setContactTyping] = useState(false);
  const [sending, setSending] = useState(false);

  const bottomRef = useRef<HTMLDivElement | null>(null);
  const composerRef = useRef<HTMLTextAreaElement | null>(null);
  const selectedRef = useRef<string | null>(null);
  useEffect(() => {
    selectedRef.current = selectedId;
  }, [selectedId]);

  const mergeMessages = useCallback((incoming: Message[]) => {
    setMessages((prev) => {
      const bySeq = new Map<number, Message>();
      for (const m of prev) bySeq.set(m.seq, m);
      for (const m of incoming) bySeq.set(m.seq, m);
      return Array.from(bySeq.values()).sort((a, b) => a.seq - b.seq);
    });
  }, []);

  const loadConversations = useCallback(async () => {
    const params = new URLSearchParams();
    if (status !== "all") params.set("status", status);
    if (channel !== "all") params.set("channel", channel);
    if (mineOnly && user) params.set("assignee_id", user.id);
    if (search.trim()) params.set("search", search.trim());
    try {
      const data = await authFetch<ConversationList>(
        `/api/conversations?${params.toString()}`,
      );
      setConversations(data.items);
      setSelectedId((cur) => cur ?? data.items[0]?.id ?? null);
    } catch {
      /* transient — refreshed by the next event */
    } finally {
      setLoading(false);
    }
  }, [authFetch, status, channel, mineOnly, search, user]);

  useEffect(() => {
    setLoading(true);
    const t = setTimeout(loadConversations, search ? 300 : 0);
    return () => clearTimeout(t);
  }, [loadConversations, search]);

  useEffect(() => {
    authFetch<TeamMember[]>("/api/team/members").then(setMembers).catch(() => {});
  }, [authFetch]);

  useEffect(() => {
    if (!selectedId) {
      setDetail(null);
      setMessages([]);
      return;
    }
    let cancelled = false;
    setThreadLoading(true);
    (async () => {
      try {
        const data = await authFetch<ConversationDetail>(
          `/api/conversations/${selectedId}`,
        );
        if (cancelled) return;
        setDetail(data);
        setMessages(data.messages);
        setContactTyping(false);
        const top = data.messages.at(-1)?.seq ?? 0;
        if (top > 0) {
          authFetch(`/api/conversations/${selectedId}/read?up_to_seq=${top}`, {
            method: "POST",
          }).catch(() => {});
          setConversations((prev) =>
            prev.map((c) =>
              c.id === selectedId ? { ...c, unread_count: 0 } : c,
            ),
          );
        }
      } catch {
        /* ignore */
      } finally {
        if (!cancelled) setThreadLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [selectedId, authFetch]);

  useEffect(() => {
    if (!socket || !selectedId || !connected) return;
    socket.emit(
      "join_conversation",
      { conversation_id: selectedId, last_seq: 0 },
      (res: { ok: boolean; missed?: Message[] }) => {
        if (res?.ok && res.missed?.length) mergeMessages(res.missed);
      },
    );
    return () => {
      socket.emit("leave_conversation", { conversation_id: selectedId });
    };
  }, [socket, selectedId, connected, mergeMessages]);

  useEffect(() => {
    if (!socket) return;
    const onMessage = (m: Message) => {
      if (m.conversation_id === selectedRef.current) {
        mergeMessages([m]);
        if (m.sender_type === "contact") setContactTyping(false);
      }
    };
    const refresh = () => loadConversations();
    const onTyping = (d: { sender_type: string; is_typing: boolean }) => {
      if (d.sender_type === "contact") setContactTyping(d.is_typing);
    };
    const onRead = (d: {
      conversation_id: string;
      reader: string;
      up_to_seq: number;
    }) => {
      if (d.reader !== "contact" || d.conversation_id !== selectedRef.current)
        return;
      setMessages((prev) =>
        prev.map((m) =>
          m.sender_type === "agent" && m.seq <= d.up_to_seq && !m.read_at
            ? { ...m, read_at: new Date().toISOString() }
            : m,
        ),
      );
    };

    socket.on("message:new", onMessage);
    socket.on("inbox:message", refresh);
    socket.on("conversation:updated", refresh);
    socket.on("typing", onTyping);
    socket.on("message:read", onRead);
    return () => {
      socket.off("message:new", onMessage);
      socket.off("inbox:message", refresh);
      socket.off("conversation:updated", refresh);
      socket.off("typing", onTyping);
      socket.off("message:read", onRead);
    };
  }, [socket, mergeMessages, loadConversations]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, contactTyping]);

  const send = async () => {
    const body = draft.trim();
    if (!body || !selectedId || sending) return;
    setDraft("");
    setSending(true);
    if (socket && connected && detail?.channel === "chat") {
      socket.emit(
        "send_message",
        { conversation_id: selectedId, body },
        (res: { ok: boolean; message?: Message }) => {
          if (res?.ok && res.message) mergeMessages([res.message]);
          setSending(false);
        },
      );
    } else {
      try {
        const m = await authFetch<Message>(
          `/api/conversations/${selectedId}/messages`,
          { method: "POST", body: { body } },
        );
        mergeMessages([m]);
      } finally {
        setSending(false);
      }
    }
  };

  const act = async (path: string, body: unknown) => {
    if (!selectedId) return;
    try {
      const updated = await authFetch<Conversation>(
        `/api/conversations/${selectedId}/${path}`,
        { method: "POST", body },
      );
      setDetail((d) => (d ? { ...d, ...updated } : d));
      loadConversations();
    } catch {
      /* ignore */
    }
  };

  /** Group messages by calendar day for date separators. */
  const grouped = useMemo(() => {
    const out: { day: string; items: Message[] }[] = [];
    for (const m of messages) {
      const day = dayLabel(m.created_at);
      const last = out.at(-1);
      if (last && last.day === day) last.items.push(m);
      else out.push({ day, items: [m] });
    }
    return out;
  }, [messages]);

  return (
    <div className="flex h-full">
      {/* ── List ─────────────────────────────────────────────────────── */}
      <div className="flex w-[340px] shrink-0 flex-col border-r border-neutral-200 bg-white">
        <div className="px-4 pb-2 pt-3.5">
          <div className="flex items-center justify-between">
            <h1 className="text-[17px] font-bold tracking-tight">Inbox</h1>
            <span
              className={`inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-[11px] font-medium ${
                connected
                  ? "bg-emerald-50 text-emerald-700"
                  : "bg-neutral-100 text-neutral-500"
              }`}
              title={connected ? "Realtime connected" : "Reconnecting…"}
            >
              <span
                className={`h-1.5 w-1.5 rounded-full ${
                  connected ? "bg-emerald-500" : "bg-neutral-400"
                }`}
              />
              {connected ? "Live" : "Offline"}
            </span>
          </div>

          <div className="relative mt-2.5">
            <svg
              width="15"
              height="15"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-neutral-400"
            >
              <circle cx="11" cy="11" r="8" />
              <path d="m21 21-4.3-4.3" />
            </svg>
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search conversations"
              className="focus-ring w-full rounded-lg border border-neutral-300 bg-white py-1.5 pl-8 pr-3 text-sm placeholder:text-neutral-400"
            />
          </div>
        </div>

        <div className="flex items-center gap-1 px-3 pb-2">
          {STATUS_TABS.map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => setStatus(s)}
              className={`rounded-md px-2 py-1 text-xs font-medium capitalize transition ${
                status === s
                  ? "bg-neutral-900 text-white"
                  : "text-neutral-600 hover:bg-neutral-100"
              }`}
            >
              {s}
            </button>
          ))}
        </div>

        <div className="flex items-center gap-1 border-b border-neutral-200 px-3 pb-2.5">
          {CHANNEL_TABS.map((c) => (
            <button
              key={c}
              type="button"
              onClick={() => setChannel(c)}
              className={`rounded-md px-2 py-1 text-xs font-medium capitalize transition ${
                channel === c
                  ? "bg-brand-50 text-brand-700"
                  : "text-neutral-600 hover:bg-neutral-100"
              }`}
            >
              {c}
            </button>
          ))}
          <button
            type="button"
            onClick={() => setMineOnly((v) => !v)}
            className={`ml-auto rounded-md px-2 py-1 text-xs font-medium transition ${
              mineOnly
                ? "bg-brand-50 text-brand-700"
                : "text-neutral-600 hover:bg-neutral-100"
            }`}
          >
            Assigned to me
          </button>
        </div>

        <div className="scroll-thin flex-1 overflow-y-auto">
          {loading ? (
            <div className="space-y-3 p-4">
              {[0, 1, 2, 3].map((i) => (
                <div key={i} className="flex gap-3">
                  <div className="skeleton h-9 w-9 rounded-full" />
                  <div className="flex-1 space-y-2">
                    <div className="skeleton h-3 w-1/2 rounded" />
                    <div className="skeleton h-3 w-3/4 rounded" />
                  </div>
                </div>
              ))}
            </div>
          ) : conversations.length === 0 ? (
            <EmptyState
              icon={
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M22 12h-6l-2 3h-4l-2-3H2" />
                  <path d="M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z" />
                </svg>
              }
              title="Nothing here"
              description={
                search
                  ? "No conversations match your search."
                  : "New chats and emails will show up here."
              }
            />
          ) : (
            conversations.map((c) => {
              const active = selectedId === c.id;
              const unread = c.unread_count > 0;
              return (
                <button
                  key={c.id}
                  type="button"
                  onClick={() => setSelectedId(c.id)}
                  className={`relative flex w-full gap-3 border-b border-neutral-100 px-4 py-3 text-left transition ${
                    active ? "bg-brand-50/60" : "hover:bg-neutral-50"
                  }`}
                >
                  {active && (
                    <span className="absolute inset-y-0 left-0 w-0.5 bg-brand" />
                  )}
                  <Avatar name={displayName(c.contact)} size={36} />
                  <span className="min-w-0 flex-1">
                    <span className="flex items-baseline justify-between gap-2">
                      <span
                        className={`truncate text-sm ${
                          unread ? "font-bold" : "font-semibold"
                        }`}
                      >
                        {displayName(c.contact)}
                      </span>
                      <span className="shrink-0 text-[11px] text-neutral-400">
                        {timeAgo(c.last_message_at ?? c.created_at)}
                      </span>
                    </span>
                    <span
                      className={`mt-0.5 block truncate text-xs ${
                        unread ? "font-medium text-neutral-800" : "text-neutral-500"
                      }`}
                    >
                      {c.last_message_preview || "No messages yet"}
                    </span>
                    <span className="mt-1.5 flex items-center gap-1.5">
                      <Badge tone={c.channel === "chat" ? "brand" : "outline"}>
                        {c.channel}
                      </Badge>
                      {c.status !== "open" && (
                        <Badge tone={c.status === "resolved" ? "green" : "amber"}>
                          {c.status}
                        </Badge>
                      )}
                      {c.assignee && (
                        <span className="ml-auto" title={`Assigned to ${c.assignee.name || c.assignee.email}`}>
                          <Avatar name={c.assignee.name || c.assignee.email} size={18} />
                        </span>
                      )}
                      {unread && (
                        <span className="ml-auto rounded-full bg-brand px-1.5 py-px text-[10px] font-bold text-white">
                          {c.unread_count}
                        </span>
                      )}
                    </span>
                  </span>
                </button>
              );
            })
          )}
        </div>
      </div>

      {/* ── Thread ───────────────────────────────────────────────────── */}
      <div className="flex min-w-0 flex-1 flex-col bg-neutral-50">
        {!detail ? (
          <div className="flex flex-1 items-center justify-center">
            <EmptyState
              icon={
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
                </svg>
              }
              title="No conversation selected"
              description="Pick a conversation from the list to read and reply."
            />
          </div>
        ) : (
          <>
            <header className="flex flex-wrap items-center gap-2.5 border-b border-neutral-200 bg-white px-5 py-3">
              <Avatar name={displayName(detail.contact)} size={36} />
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-semibold leading-tight">
                  {displayName(detail.contact)}
                </p>
                <p className="truncate text-xs text-neutral-500">
                  {detail.channel === "email"
                    ? detail.subject || detail.contact.email
                    : detail.contact.email || "Live chat visitor"}
                </p>
              </div>

              <Select
                value={detail.assignee?.id ?? ""}
                onChange={(e) =>
                  act("assign", { assignee_id: e.target.value || null })
                }
                className="!py-1.5 text-xs"
              >
                <option value="">Unassigned</option>
                {members.map((m) => (
                  <option key={m.user_id} value={m.user_id}>
                    {m.name || m.email}
                  </option>
                ))}
              </Select>

              {detail.status !== "resolved" ? (
                <>
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={() =>
                      act("status", {
                        status: "snoozed",
                        snoozed_until: new Date(
                          Date.now() + 24 * 3600 * 1000,
                        ).toISOString(),
                      })
                    }
                  >
                    Snooze
                  </Button>
                  <Button size="sm" onClick={() => act("status", { status: "resolved" })}>
                    Resolve
                  </Button>
                </>
              ) : (
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => act("status", { status: "open" })}
                >
                  Reopen
                </Button>
              )}
            </header>

            <div className="scroll-thin flex-1 overflow-y-auto px-6 py-5">
              {threadLoading && messages.length === 0 ? (
                <div className="space-y-4">
                  {[0, 1, 2].map((i) => (
                    <div
                      key={i}
                      className={`flex ${i % 2 ? "justify-end" : "justify-start"}`}
                    >
                      <div className="skeleton h-12 w-64 rounded-2xl" />
                    </div>
                  ))}
                </div>
              ) : messages.length === 0 ? (
                <EmptyState
                  title="No messages yet"
                  description="Say hello — your reply starts the conversation."
                />
              ) : (
                grouped.map((group) => (
                  <div key={group.day}>
                    <div className="my-4 flex items-center gap-3">
                      <span className="h-px flex-1 bg-neutral-200" />
                      <span className="text-[11px] font-medium text-neutral-400">
                        {group.day}
                      </span>
                      <span className="h-px flex-1 bg-neutral-200" />
                    </div>
                    <div className="space-y-2.5">
                      {group.items.map((m) => {
                        const mine = m.sender_type === "agent";
                        return (
                          <div
                            key={m.seq}
                            className={`flex items-end gap-2 ${
                              mine ? "justify-end" : "justify-start"
                            }`}
                          >
                            {!mine && (
                              <Avatar name={displayName(detail.contact)} size={26} />
                            )}
                            <div
                              className={`animate-msg-in max-w-[68%] rounded-2xl px-3.5 py-2.5 text-sm leading-relaxed shadow-sm ${
                                mine
                                  ? "rounded-br-md bg-brand text-white"
                                  : "rounded-bl-md border border-neutral-200 bg-white text-neutral-800"
                              }`}
                            >
                              <p className="whitespace-pre-wrap break-words">
                                {m.body}
                              </p>
                              <span
                                className={`mt-1 flex items-center gap-1 text-[10px] ${
                                  mine ? "text-white/70" : "text-neutral-400"
                                }`}
                              >
                                {new Date(m.created_at).toLocaleTimeString([], {
                                  hour: "2-digit",
                                  minute: "2-digit",
                                })}
                                {mine && (
                                  <>
                                    <span>·</span>
                                    {m.read_at ? "Read" : "Sent"}
                                  </>
                                )}
                              </span>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                ))
              )}

              {contactTyping && (
                <div className="mt-2.5 flex items-end gap-2">
                  <Avatar name={displayName(detail.contact)} size={26} />
                  <div className="rounded-2xl rounded-bl-md border border-neutral-200 bg-white px-4 py-3 shadow-sm">
                    <span className="flex gap-1">
                      {[0, 150, 300].map((d) => (
                        <span
                          key={d}
                          className="h-1.5 w-1.5 animate-bounce rounded-full bg-neutral-400"
                          style={{ animationDelay: `${d}ms` }}
                        />
                      ))}
                    </span>
                  </div>
                </div>
              )}
              <div ref={bottomRef} />
            </div>

            <div className="border-t border-neutral-200 bg-white p-3">
              <div className="focus-within:border-brand focus-within:ring-4 focus-within:ring-brand/10 flex items-end gap-2 rounded-xl border border-neutral-300 bg-white p-2 transition">
                <textarea
                  ref={composerRef}
                  value={draft}
                  onChange={(e) => setDraft(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && !e.shiftKey) {
                      e.preventDefault();
                      send();
                    }
                  }}
                  rows={1}
                  placeholder={
                    detail.channel === "email"
                      ? "Write a reply — sends as an email…"
                      : "Write a reply…"
                  }
                  className="max-h-32 min-h-[36px] flex-1 resize-none bg-transparent px-1.5 py-1.5 text-sm outline-none placeholder:text-neutral-400"
                />
                <Button onClick={send} loading={sending} disabled={!draft.trim()}>
                  Send
                </Button>
              </div>
              <p className="mt-1.5 px-1 text-[11px] text-neutral-400">
                <kbd className="rounded border border-neutral-200 bg-neutral-50 px-1">
                  Enter
                </kbd>{" "}
                to send ·{" "}
                <kbd className="rounded border border-neutral-200 bg-neutral-50 px-1">
                  Shift+Enter
                </kbd>{" "}
                for a new line
              </p>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
