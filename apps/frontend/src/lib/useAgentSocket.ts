"use client";

import { useEffect, useRef, useState } from "react";
import { io, type Socket } from "socket.io-client";

const SOCKET_URL =
  process.env.NEXT_PUBLIC_SOCKET_URL ?? "http://localhost:8000";

/**
 * Shared agent Socket.IO connection.
 *
 * The socket is created once per access token and torn down on logout. Callers
 * subscribe to events with `socket.on(...)` in their own effects.
 */
export function useAgentSocket(accessToken: string | null) {
  const [socket, setSocket] = useState<Socket | null>(null);
  const [connected, setConnected] = useState(false);
  const ref = useRef<Socket | null>(null);

  useEffect(() => {
    if (!accessToken) {
      ref.current?.disconnect();
      ref.current = null;
      setSocket(null);
      setConnected(false);
      return;
    }

    const s = io(SOCKET_URL, {
      path: "/socket.io",
      transports: ["websocket"],
      auth: { token: accessToken },
      reconnection: true,
      reconnectionDelay: 500,
      reconnectionDelayMax: 5000,
    });

    ref.current = s;
    setSocket(s);

    s.on("connect", () => setConnected(true));
    s.on("disconnect", () => setConnected(false));
    s.on("connect_error", () => setConnected(false));

    const beat = setInterval(() => s.emit("heartbeat", {}), 25000);

    return () => {
      clearInterval(beat);
      s.removeAllListeners();
      s.disconnect();
      ref.current = null;
    };
  }, [accessToken]);

  return { socket, connected };
}
