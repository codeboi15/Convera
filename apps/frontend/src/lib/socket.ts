"use client";

import { io, type Socket } from "socket.io-client";
import { SOCKET_OPTIONS, SOCKET_URL } from "@/lib/config";

let socket: Socket | null = null;

/**
 * Lazily create a shared Socket.IO connection. Auth (JWT or anonymous widget
 * token) is passed via the `auth` payload and validated server-side.
 */
export function getSocket(auth?: Record<string, unknown>): Socket {
  if (!socket) {
    socket = io(SOCKET_URL, {
      ...SOCKET_OPTIONS,
      autoConnect: false,
      auth: auth ?? {},
    });
  }
  return socket;
}

export function disconnectSocket(): void {
  socket?.disconnect();
  socket = null;
}
