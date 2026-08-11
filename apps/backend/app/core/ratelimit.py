import logging
import time
from typing import Optional

import redis.asyncio as aioredis
from fastapi import HTTPException, Request, Response, status

from app.core.config import settings

logger = logging.getLogger(__name__)

_redis: Optional[aioredis.Redis] = None
_redis_unavailable_logged = False


def _client() -> Optional[aioredis.Redis]:
    global _redis
    if _redis is None and settings.redis_url:
        try:
            _redis = aioredis.from_url(
                settings.redis_url, encoding="utf-8", decode_responses=True
            )
        except Exception:  # pragma: no cover - malformed URL
            logger.exception("could not create redis client for rate limiting")
            return None
    return _redis


def client_ip(request: Request) -> str:
    """Best-effort client address.

    Behind Railway/Vercel the socket peer is the platform's proxy, so the real
    address is the first entry of ``X-Forwarded-For``. That header is only
    trustworthy because the platform rewrites it — if this ever runs without a
    proxy in front, the value is attacker-controlled.
    """
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        first = forwarded.split(",")[0].strip()
        if first:
            return first
    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        return real_ip.strip()
    return request.client.host if request.client else "unknown"


class RateLimit:
    """Fixed-window rate limit, enforced with Redis counters.

    Used as a FastAPI dependency so each route can declare its own budget::

        @router.post("/login", dependencies=[Depends(RateLimit("login", 10, 60))])

    To key on something other than the client address (a workspace, a user),
    call :meth:`check` directly from the handler with that identity.

    **Fails open.** If Redis is unreachable the request is allowed rather than
    rejected — a limiter that takes the API down when its datastore blips is
    worse than the abuse it prevents. The condition is logged once so it is
    visible without flooding the log.
    """

    def __init__(
        self,
        scope: str,
        limit: int,
        window_seconds: int,
    ) -> None:
        self.scope = scope
        self.limit = limit
        self.window = window_seconds

    async def check(self, identity: str, response: Optional[Response] = None) -> None:
        """Count one hit against ``identity``; raise 429 when over budget."""
        redis = _client()
        if redis is None:
            self._warn_unavailable()
            return

        window_start = int(time.time()) // self.window
        redis_key = f"ratelimit:{self.scope}:{identity}:{window_start}"

        try:
            pipe = redis.pipeline()
            pipe.incr(redis_key)
            # Only the first hit needs a TTL; EXPIRE on every call would keep
            # sliding the window forward and never reset the counter.
            pipe.expire(redis_key, self.window, nx=True)
            current = (await pipe.execute())[0]
        except Exception:
            self._warn_unavailable()
            return

        remaining = max(0, self.limit - int(current))
        if response is not None:
            response.headers["X-RateLimit-Limit"] = str(self.limit)
            response.headers["X-RateLimit-Remaining"] = str(remaining)

        if int(current) > self.limit:
            retry_after = self.window - (int(time.time()) % self.window)
            logger.info(
                "rate limit exceeded scope=%s identity=%s count=%s limit=%s",
                self.scope,
                identity,
                current,
                self.limit,
            )
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many requests. Please slow down and try again shortly.",
                headers={
                    "Retry-After": str(retry_after),
                    "X-RateLimit-Limit": str(self.limit),
                    "X-RateLimit-Remaining": "0",
                },
            )

    def _warn_unavailable(self) -> None:
        global _redis_unavailable_logged
        if not _redis_unavailable_logged:
            logger.warning(
                "Redis unavailable — rate limiting is disabled (failing open). "
                "Set REDIS_URL to enforce limits."
            )
            _redis_unavailable_logged = True

    async def __call__(self, request: Request, response: Response) -> None:
        # NB: this module deliberately does *not* use
        # ``from __future__ import annotations``. FastAPI resolves string
        # annotations against the callable's ``__globals__``, which a class
        # *instance* does not have — the Request/Response parameters would be
        # mistaken for required query params and every call would 422.
        await self.check(client_ip(request), response)


def reset_client() -> None:
    """Drop the cached Redis client (used by tests)."""
    global _redis, _redis_unavailable_logged
    _redis = None
    _redis_unavailable_logged = False
