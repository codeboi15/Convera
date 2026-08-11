from __future__ import annotations

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings

from app.core.config import settings


def redis_settings() -> RedisSettings:
    """Parse REDIS_URL into arq settings.

    Raised at worker start-up, so surface a message that names the actual
    problem — arq's own error is a bare "invalid DSN scheme", which is very
    hard to diagnose from a container log.
    """
    url = (settings.redis_url or "").strip()
    if not url:
        raise RuntimeError(
            "REDIS_URL is not set. The worker needs Redis for its job queue — "
            "add the Redis plugin and set REDIS_URL (e.g. ${{Redis.REDIS_URL}})."
        )
    if not url.startswith(("redis://", "rediss://", "unix://")):
        raise RuntimeError(
            f"REDIS_URL has an unsupported scheme: {url.split('://', 1)[0]!r}. "
            "Expected redis://, rediss:// or unix://."
        )
    return RedisSettings.from_dsn(url)


async def get_queue() -> ArqRedis:
    """Create an arq Redis pool for enqueuing jobs from the API process."""
    return await create_pool(redis_settings())
