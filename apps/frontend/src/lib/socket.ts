"use client";

import { io, type Socket } from "socket.io-client";

const SOCKET_URL =
  process.env.NEXT_PUBLIC_SOCKET_URL ?? "http://localhost:8000";

let socket: Socket | null = null;

/**
 * Lazily create a shared Socket.IO connection. Auth (JWT or anonymous widget
 * token) is passed via the `auth` payload and validated server-side.
 */
export function getSocket(auth?: Record<string, unknown>): Socket {
  if (!socket) {
    socket = io(SOCKET_URL, {
      path: "/socket.io",
      transports: ["websocket"],
      autoConnect: false,
      auth: auth ?? {},
      reconnection: true,
      reconnectionDelay: 500,
      reconnectionDelayMax: 5000,
    });
  }
  return socket;
}

export function disconnectSocket(): void {
  socket?.disconnect();
  socket = null;
}
