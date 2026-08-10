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
import { Badge, Button } from "@/components/ui";

type StatusFilter = "open" | "snoozed" | "resolved" | "all";
type ChannelFilter = "chat" | "email" | "all";

function timeAgo(iso?: string | null): string {
  if (!iso) return "";
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "now";
  if (mins < 60) return `${mins}m`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h`;
  return `${Math.floor(hrs / 24)}d`;
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
  const [loading, setLoading] = useState(true);
  const [contactTyping, setContactTyping] = useState(false);
  const [sending, setSending] = useState(false);

  const bottomRef = useRef<HTMLDivElement | null>(null);
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
    try {
      const data = await authFetch<ConversationList>(
        `/api/conversations?${params.toString()}`,
      );
      setConversations(data.items);
      setSelectedId((cur) => cur ?? data.items[0]?.id ?? null);
    } catch {
      /* transient; the list refreshes on the next event */
    } finally {
      setLoading(false);
    }
  }, [authFetch, status, channel, mineOnly, user]);

  useEffect(() => {
    setLoading(true);
    loadConversations();
  }, [loadConversations]);

  useEffect(() => {
    authFetch<TeamMember[]>("/api/team/members").then(setMembers).catch(() => {});
  }, [authFetch]);

  // Load the selected thread.
  useEffect(() => {
    if (!selectedId) {
      setDetail(null);
      setMessages([]);
      return;
    }
    let cancelled = false;
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
          authFetch(
            `/api/conversations/${selectedId}/read?up_to_seq=${top}`,
            { method: "POST" },
          ).catch(() => {});
          setConversations((prev) =>
            prev.map((c) => (c.id === selectedId ? { ...c, unread_count: 0 } : c)),
          );
        }
      } catch {
        /* ignore */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [selectedId, authFetch]);

  // Join the conversation room, replaying anything missed.
  useEffect(() => {
    if (!socket || !selectedId || !connected) return;
    const lastSeq = messages.at(-1)?.seq ?? 0;
    socket.emit(
      "join_conversation",
      { conversation_id: selectedId, last_seq: lastSeq },
      (res: { ok: boolean; missed?: Message[] }) => {
        if (res?.ok && res.missed?.length) mergeMessages(res.missed);
      },
    );
    return () => {
      socket.emit("leave_conversation", { conversation_id: selectedId });
    };
    // messages intentionally omitted: re-joining on every message would thrash
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [socket, selectedId, connected, mergeMessages]);

  // Realtime subscriptions.
  useEffect(() => {
    if (!socket) return;

    const onMessage = (m: Message) => {
      if (m.conversation_id === selectedRef.current) {
        mergeMessages([m]);
        if (m.sender_type === "contact") setContactTyping(false);
      }
    };
    const onInbox = () => loadConversations();
    const onTyping = (d: { sender_type: string; is_typing: boolean }) => {
      if (d.sender_type === "contact") setContactTyping(d.is_typing);
    };
    const onRead = (d: { conversation_id: string; reader: string; up_to_seq: number }) => {
      if (d.reader !== "contact" || d.conversation_id !== selectedRef.current) return;
      setMessages((prev) =>
        prev.map((m) =>
          m.sender_type === "agent" && m.seq <= d.up_to_seq && !m.read_at
            ? { ...m, read_at: new Date().toISOString() }
            : m,
        ),
      );
    };

    socket.on("message:new", onMessage);
    socket.on("inbox:message", onInbox);
    socket.on("conversation:updated", onInbox);
    socket.on("typing", onTyping);
    socket.on("message:read", onRead);

    return () => {
      socket.off("message:new", onMessage);
      socket.off("inbox:message", onInbox);
      socket.off("conversation:updated", onInbox);
      socket.off("typing", onTyping);
      socket.off("message:read", onRead);
    };
  }, [socket, mergeMessages, loadConversations]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const send = async (e: React.FormEvent) => {
    e.preventDefault();
    const body = draft.trim();
    if (!body || !selectedId) return;
    setDraft("");
    setSending(true);

    // Chat goes over the socket; email replies use REST so the worker can queue them.
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

  const filters = useMemo(
    () => (
      <div className="flex flex-wrap items-center gap-1.5 border-b border-neutral-200 px-3 py-2">
        {(["open", "snoozed", "resolved", "all"] as StatusFilter[]).map((s) => (
          <button
            key={s}
            type="button"
            onClick={() => setStatus(s)}
            className={`rounded-full px-2.5 py-1 text-xs font-medium capitalize transition ${
              status === s
                ? "bg-brand text-white"
                : "text-neutral-600 hover:bg-neutral-100"
            }`}
          >
            {s}
          </button>
        ))}
        <span className="mx-1 h-4 w-px bg-neutral-200" />
        {(["all", "chat", "email"] as ChannelFilter[]).map((c) => (
          <button
            key={c}
            type="button"
            onClick={() => setChannel(c)}
            className={`rounded-full px-2.5 py-1 text-xs font-medium capitalize transition ${
              channel === c
                ? "bg-neutral-800 text-white"
                : "text-neutral-600 hover:bg-neutral-100"
            }`}
          >
            {c}
          </button>
        ))}
        <button
          type="button"
          onClick={() => setMineOnly((v) => !v)}
          className={`ml-auto rounded-full px-2.5 py-1 text-xs font-medium transition ${
            mineOnly ? "bg-brand text-white" : "text-neutral-600 hover:bg-neutral-100"
          }`}
        >
          Mine
        </button>
      </div>
    ),
    [status, channel, mineOnly],
  );

  return (
    <div className="flex h-full">
      {/* Conversation list */}
      <div className="flex w-80 shrink-0 flex-col border-r border-neutral-200 bg-white">
        <div className="flex items-center justify-between px-4 py-3">
          <h1 className="font-bold tracking-tight">Inbox</h1>
          <span
            className={`flex items-center gap-1.5 text-xs ${
              connected ? "text-green-600" : "text-neutral-400"
            }`}
          >
            <span
              className={`h-1.5 w-1.5 rounded-full ${
                connected ? "bg-green-500" : "bg-neutral-300"
              }`}
            />
            {connected ? "Live" : "Offline"}
          </span>
        </div>
        {filters}
        <div className="flex-1 overflow-y-auto">
          {loading ? (
            <p className="p-4 text-sm text-neutral-500">Loading…</p>
          ) : conversations.length === 0 ? (
            <p className="p-4 text-sm text-neutral-500">
              No conversations here yet.
            </p>
          ) : (
            conversations.map((c) => (
              <button
                key={c.id}
                type="button"
                onClick={() => setSelectedId(c.id)}
                className={`w-full border-b border-neutral-100 px-4 py-3 text-left transition hover:bg-neutral-50 ${
                  selectedId === c.id ? "bg-brand/5" : ""
                }`}
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="truncate text-sm font-semibold">
                    {c.contact.name || c.contact.email || "Anonymous visitor"}
                  </span>
                  <span className="shrink-0 text-xs text-neutral-400">
                    {timeAgo(c.last_message_at ?? c.created_at)}
                  </span>
                </div>
                <p className="mt-0.5 truncate text-xs text-neutral-500">
                  {c.last_message_preview || "No messages yet"}
                </p>
                <div className="mt-1.5 flex items-center gap-1.5">
                  <Badge tone={c.channel === "chat" ? "brand" : "neutral"}>
                    {c.channel}
                  </Badge>
                  {c.status !== "open" && <Badge tone="amber">{c.status}</Badge>}
                  {c.unread_count > 0 && (
                    <span className="ml-auto rounded-full bg-brand px-1.5 text-xs font-semibold text-white">
                      {c.unread_count}
                    </span>
                  )}
                </div>
              </button>
            ))
          )}
        </div>
      </div>

      {/* Thread */}
      <div className="flex min-w-0 flex-1 flex-col bg-neutral-50">
        {!detail ? (
          <div className="flex flex-1 items-center justify-center text-sm text-neutral-500">
            Select a conversation to get started.
          </div>
        ) : (
          <>
            <header className="flex flex-wrap items-center gap-2 border-b border-neutral-200 bg-white px-4 py-3">
              <div className="min-w-0 flex-1">
                <p className="truncate font-semibold">
                  {detail.contact.name || detail.contact.email || "Anonymous visitor"}
                </p>
                <p className="truncate text-xs text-neutral-500">
                  {detail.channel === "email"
                    ? detail.subject || detail.contact.email
                    : "Live chat"}
                </p>
              </div>

              <select
                value={detail.assignee?.id ?? ""}
                onChange={(e) =>
                  act("assign", { assignee_id: e.target.value || null })
                }
                className="rounded-lg border border-neutral-300 px-2 py-1.5 text-xs outline-none focus:border-brand"
              >
                <option value="">Unassigned</option>
                {members.map((m) => (
                  <option key={m.user_id} value={m.user_id}>
                    {m.name || m.email}
                  </option>
                ))}
              </select>

              {detail.status !== "resolved" ? (
                <>
                  <Button
                    variant="secondary"
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
                  <Button onClick={() => act("status", { status: "resolved" })}>
                    Resolve
                  </Button>
                </>
              ) : (
                <Button
                  variant="secondary"
                  onClick={() => act("status", { status: "open" })}
                >
                  Reopen
                </Button>
              )}
            </header>

            <div className="flex-1 space-y-3 overflow-y-auto px-6 py-5">
              {messages.map((m) => {
                const mine = m.sender_type === "agent";
                return (
                  <div
                    key={m.seq}
                    className={`flex ${mine ? "justify-end" : "justify-start"}`}
                  >
                    <div
                      className={`max-w-[70%] whitespace-pre-wrap break-words rounded-2xl px-4 py-2.5 text-sm shadow-sm ${
                        mine
                          ? "rounded-br-sm bg-brand text-white"
                          : "rounded-bl-sm border border-neutral-200 bg-white"
                      }`}
                    >
                      {m.body}
                      <span
                        className={`mt-1 block text-[10px] ${
                          mine ? "text-white/70" : "text-neutral-400"
                        }`}
                      >
                        {new Date(m.created_at).toLocaleTimeString([], {
                          hour: "2-digit",
                          minute: "2-digit",
                        })}
                        {mine && (m.read_at ? " · Read" : " · Sent")}
                      </span>
                    </div>
                  </div>
                );
              })}
              {contactTyping && (
                <div className="flex justify-start">
                  <div className="rounded-2xl rounded-bl-sm border border-neutral-200 bg-white px-4 py-3">
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

            <form
              onSubmit={send}
              className="flex gap-2 border-t border-neutral-200 bg-white p-3"
            >
              <input
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                placeholder={
                  detail.channel === "email"
                    ? "Write a reply — sends as an email…"
                    : "Write a reply…"
                }
                className="flex-1 rounded-lg border border-neutral-300 px-3 py-2 text-sm outline-none focus:border-brand"
              />
              <Button type="submit" loading={sending} disabled={!draft.trim()}>
                Send
              </Button>
            </form>
          </>
        )}
      </div>
    </div>
  );
}
