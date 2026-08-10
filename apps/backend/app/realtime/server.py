from __future__ import annotations

import logging

import socketio

from app.core.config import settings

logger = logging.getLogger(__name__)

# Use a Redis-backed manager so messages fan out across multiple API instances.
# Falls back to the in-memory manager when no Redis URL is configured (local dev).
_manager = (
    socketio.AsyncRedisManager(settings.redis_url) if settings.redis_url else None
)

sio = socketio.AsyncServer(
    async_mode="asgi",
    client_manager=_manager,
    cors_allowed_origins=settings.cors_origin_list,
    logger=settings.debug,
    engineio_logger=False,
)


@sio.event
async def connect(sid: str, environ: dict, auth: dict | None) -> None:
    # Full auth (JWT / anonymous widget token) and room joins are wired up in the
    # live-chat step. For now just log connections.
    logger.debug("socket connected: %s", sid)


@sio.event
async def disconnect(sid: str) -> None:
    logger.debug("socket disconnected: %s", sid)
