"use client";

import { useEffect, useRef, useState } from "react";
import { io, type Socket } from "socket.io-client";
import {
  PRESENCE_HEARTBEAT_MS,
  SOCKET_OPTIONS,
  SOCKET_URL,
} from "@/lib/config";

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

    const s = io(SOCKET_URL, { ...SOCKET_OPTIONS, auth: { token: accessToken } });

    ref.current = s;
    setSocket(s);

    s.on("connect", () => setConnected(true));
    s.on("disconnect", () => setConnected(false));
    s.on("connect_error", () => setConnected(false));

    const beat = setInterval(
      () => s.emit("heartbeat", {}),
      PRESENCE_HEARTBEAT_MS,
    );

    return () => {
      clearInterval(beat);
      s.removeAllListeners();
      s.disconnect();
      ref.current = null;
    };
  }, [accessToken]);

  return { socket, connected };
}
