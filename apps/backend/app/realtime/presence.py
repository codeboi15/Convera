from __future__ import annotations

import logging
from typing import List, Optional

import redis.asyncio as aioredis

from app.core.config import settings

logger = logging.getLogger(__name__)

# Presence keys expire so a hard crash (no disconnect event) still clears state.
PRESENCE_TTL_SECONDS = 60

_redis: Optional[aioredis.Redis] = None


def _client() -> Optional[aioredis.Redis]:
    global _redis
    if _redis is None and settings.redis_url:
        try:
            _redis = aioredis.from_url(
                settings.redis_url, encoding="utf-8", decode_responses=True
            )
        except Exception:  # pragma: no cover
            logger.exception("could not create redis client for presence")
            return None
    return _redis


def _key(workspace_id: str, actor: str) -> str:
    return f"presence:{workspace_id}:{actor}"


async def mark_online(workspace_id: str, actor: str) -> None:
    client = _client()
    if client is None:
        return
    try:
        await client.set(_key(workspace_id, actor), "1", ex=PRESENCE_TTL_SECONDS)
    except Exception:  # pragma: no cover - presence is best-effort
        logger.debug("presence write failed", exc_info=True)


async def heartbeat(workspace_id: str, actor: str) -> None:
    await mark_online(workspace_id, actor)


async def mark_offline(workspace_id: str, actor: str) -> None:
    client = _client()
    if client is None:
        return
    try:
        await client.delete(_key(workspace_id, actor))
    except Exception:  # pragma: no cover
        logger.debug("presence delete failed", exc_info=True)


async def is_online(workspace_id: str, actor: str) -> bool:
    client = _client()
    if client is None:
        return False
    try:
        return bool(await client.exists(_key(workspace_id, actor)))
    except Exception:  # pragma: no cover
        return False


async def list_online_agents(workspace_id: str) -> List[str]:
    client = _client()
    if client is None:
        return []
    try:
        keys = [k async for k in client.scan_iter(f"presence:{workspace_id}:agent:*")]
        return [k.rsplit(":", 1)[-1] for k in keys]
    except Exception:  # pragma: no cover
        return []


async def any_agent_online(workspace_id: str) -> bool:
    return len(await list_online_agents(workspace_id)) > 0
