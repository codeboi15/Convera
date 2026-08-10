"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { io, type Socket } from "socket.io-client";
import { apiFetch } from "@/lib/api";
import type { Message, WidgetSession } from "@/lib/types";

const SOCKET_URL =
  process.env.NEXT_PUBLIC_SOCKET_URL ?? "http://localhost:8000";

/** localStorage key for the anonymous visitor id — this is what makes chat
 *  history survive reloads and return visits. */
const VISITOR_KEY = "intercom_visitor_id";

const DEFAULT_ACCENT = "#4f46e5";

type Status = "connecting" | "online" | "offline";

export default function WidgetChat() {
  const params = useSearchParams();
  const workspace = params.get("workspace") ?? "";
  const accent = params.get("accent") ?? DEFAULT_ACCENT;

  const [session, setSession] = useState<WidgetSession | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [draft, setDraft] = useState("");
  const [status, setStatus] = useState<Status>("connecting");
  const [agentTyping, setAgentTyping] = useState(false);
  const [agentsOnline, setAgentsOnline] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const socketRef = useRef<Socket | null>(null);
  const bottomRef = useRef<HTMLDivElement | null>(null);
  const typingSentAt = useRef(0);
  const typingTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  /** Highest seq we have — the resume point after a reconnect. */
  const lastSeq = useMemo(
    () => messages.reduce((max, m) => (m.seq > max ? m.seq : max), 0),
    [messages],
  );
  const lastSeqRef = useRef(0);
  useEffect(() => {
    lastSeqRef.current = lastSeq;
  }, [lastSeq]);

  /** Merge by seq: the server echoes our own sends back through the room, so
   *  messages must be deduped and kept in strict seq order. */
  const mergeMessages = useCallback((incoming: Message[]) => {
    setMessages((prev) => {
      const bySeq = new Map<number, Message>();
      for (const m of prev) bySeq.set(m.seq, m);
      for (const m of incoming) bySeq.set(m.seq, m);
      return Array.from(bySeq.values()).sort((a, b) => a.seq - b.seq);
    });
  }, []);

  // ── Bootstrap the session ────────────────────────────────────────────────
  useEffect(() => {
    if (!workspace) {
      setError("This widget is missing its workspace.");
      return;
    }
    let cancelled = false;

    (async () => {
      try {
        const stored =
          typeof window !== "undefined"
            ? window.localStorage.getItem(VISITOR_KEY)
            : null;
        const data = await apiFetch<WidgetSession>("/api/widget/session", {
          method: "POST",
          body: { workspace_slug: workspace, visitor_id: stored },
        });
        if (cancelled) return;
        window.localStorage.setItem(VISITOR_KEY, data.visitor_id);
        setSession(data);
        setMessages(data.messages);
        setAgentsOnline(data.agents_online);
      } catch {
        if (!cancelled) setError("We couldn't start the chat. Please try again.");
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [workspace]);

  // ── Realtime connection ──────────────────────────────────────────────────
  useEffect(() => {
    if (!session) return;

    const socket = io(SOCKET_URL, {
      path: "/socket.io",
      transports: ["websocket"],
      auth: { token: session.token },
      reconnection: true,
      reconnectionDelay: 500,
      reconnectionDelayMax: 5000,
    });
    socketRef.current = socket;

    /** Join the room and replay anything missed while disconnected. */
    const joinAndResync = () => {
      socket.emit(
        "join_conversation",
        {
          conversation_id: session.conversation_id,
          last_seq: lastSeqRef.current,
        },
        (res: { ok: boolean; missed?: Message[] }) => {
          if (res?.ok && res.missed?.length) mergeMessages(res.missed);
        },
      );
    };

    socket.on("connect", () => {
      setStatus("online");
      joinAndResync();
    });
    socket.on("disconnect", () => setStatus("offline"));
    socket.on("connect_error", () => setStatus("offline"));

    socket.on("message:new", (m: Message) => {
      if (m.conversation_id !== session.conversation_id) return;
      mergeMessages([m]);
      if (m.sender_type === "agent") setAgentTyping(false);
    });

    socket.on("typing", (data: { sender_type: string; is_typing: boolean }) => {
      if (data.sender_type === "agent") setAgentTyping(data.is_typing);
    });

    socket.on("presence", (data: { actor: string; online: boolean }) => {
      if (data.actor?.startsWith("agent:")) setAgentsOnline(data.online);
    });

    // Keep the presence TTL fresh.
    const beat = setInterval(() => socket.emit("heartbeat", {}), 25000);

    return () => {
      clearInterval(beat);
      socket.removeAllListeners();
      socket.disconnect();
      socketRef.current = null;
    };
  }, [session, mergeMessages]);

  // Auto-scroll and report unread count to the host page.
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
    const unread = messages.filter(
      (m) => m.sender_type === "agent" && !m.read_at,
    ).length;
    window.parent?.postMessage(
      { type: "intercom:unread", count: unread },
      "*",
    );
  }, [messages]);

  // Mark agent messages read while the widget is open.
  useEffect(() => {
    const socket = socketRef.current;
    if (!socket || !session || status !== "online" || lastSeq === 0) return;
    socket.emit("mark_read", {
      conversation_id: session.conversation_id,
      up_to_seq: lastSeq,
    });
  }, [lastSeq, session, status]);

  const sendTyping = (isTyping: boolean) => {
    const socket = socketRef.current;
    if (!socket || !session) return;
    socket.emit("typing", {
      conversation_id: session.conversation_id,
      is_typing: isTyping,
    });
  };

  const onDraftChange = (value: string) => {
    setDraft(value);
    const now = Date.now();
    if (now - typingSentAt.current > 1500) {
      typingSentAt.current = now;
      sendTyping(true);
    }
    if (typingTimer.current) clearTimeout(typingTimer.current);
    typingTimer.current = setTimeout(() => sendTyping(false), 1800);
  };

  const send = (e: React.FormEvent) => {
    e.preventDefault();
    const body = draft.trim();
    const socket = socketRef.current;
    if (!body || !socket || !session) return;

    setDraft("");
    sendTyping(false);
    socket.emit(
      "send_message",
      { conversation_id: session.conversation_id, body },
      (res: { ok: boolean; message?: Message }) => {
        // Authoritative message (with its server-assigned seq) comes back here.
        if (res?.ok && res.message) mergeMessages([res.message]);
      },
    );
  };

  if (error) {
    return (
      <div className="flex h-screen items-center justify-center p-6 text-center text-sm text-neutral-600">
        {error}
      </div>
    );
  }

  return (
    <div className="flex h-screen flex-col bg-white">
      <header
        className="flex items-center justify-between px-4 py-3 text-white"
        style={{ background: accent }}
      >
        <div>
          <p className="text-sm font-semibold leading-tight">
            {session?.workspace_name ?? "Support"}
          </p>
          <p className="flex items-center gap-1.5 text-xs opacity-90">
            <span
              className="inline-block h-1.5 w-1.5 rounded-full"
              style={{ background: agentsOnline ? "#4ade80" : "#d1d5db" }}
            />
            {agentsOnline ? "We're online" : "We'll reply by email"}
          </p>
        </div>
        <button
          type="button"
          onClick={() => window.parent?.postMessage({ type: "intercom:close" }, "*")}
          aria-label="Close chat"
          className="rounded p-1 text-white/80 transition hover:bg-white/15 hover:text-white"
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
            <path d="M18 6 6 18M6 6l12 12" />
          </svg>
        </button>
      </header>

      {status === "offline" && (
        <p className="bg-amber-50 px-4 py-1.5 text-center text-xs text-amber-700">
          Reconnecting…
        </p>
      )}

      <div className="scroll-thin flex-1 space-y-2.5 overflow-y-auto bg-neutral-50 px-4 py-4">
        {messages.length === 0 && (
          <div className="mt-8 px-4 text-center">
            <span
              className="mx-auto flex h-11 w-11 items-center justify-center rounded-full text-white"
              style={{ background: accent }}
            >
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z" />
              </svg>
            </span>
            <p className="mt-3 text-sm font-semibold text-neutral-800">
              Start the conversation
            </p>
            <p className="mt-1 text-sm text-neutral-500">
              Ask us anything — we usually reply in a few minutes.
            </p>
          </div>
        )}
        {messages.map((m) => {
          const mine = m.sender_type === "contact";
          return (
            <div
              key={m.seq}
              className={`flex ${mine ? "justify-end" : "justify-start"}`}
            >
              <div
                className={`animate-msg-in max-w-[82%] rounded-2xl px-3.5 py-2.5 text-sm leading-relaxed shadow-sm ${
                  mine
                    ? "rounded-br-md text-white"
                    : "rounded-bl-md border border-neutral-200 bg-white text-neutral-800"
                }`}
                style={mine ? { background: accent } : undefined}
              >
                <p className="whitespace-pre-wrap break-words">{m.body}</p>
                <span
                  className={`mt-1 block text-[10px] ${
                    mine ? "text-white/70" : "text-neutral-400"
                  }`}
                >
                  {new Date(m.created_at).toLocaleTimeString([], {
                    hour: "2-digit",
                    minute: "2-digit",
                  })}
                  {mine && ` · ${m.read_at ? "Read" : "Sent"}`}
                </span>
              </div>
            </div>
          );
        })}
        {agentTyping && (
          <div className="flex justify-start">
            <div className="rounded-2xl rounded-bl-sm border border-neutral-200 bg-white px-3.5 py-2.5">
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

      <form onSubmit={send} className="flex gap-2 border-t border-neutral-200 p-3">
        <input
          value={draft}
          onChange={(e) => onDraftChange(e.target.value)}
          placeholder="Type your message…"
          maxLength={20000}
          className="flex-1 rounded-full border border-neutral-300 px-4 py-2 text-sm outline-none focus:border-neutral-400"
        />
        <button
          type="submit"
          disabled={!draft.trim() || !session}
          aria-label="Send message"
          className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-white transition disabled:opacity-40"
          style={{ background: accent }}
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="m22 2-7 20-4-9-9-4Z" />
          </svg>
        </button>
      </form>
    </div>
  );
}
