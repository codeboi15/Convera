from __future__ import annotations

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings

from app.core.config import settings


def redis_settings() -> RedisSettings:
    return RedisSettings.from_dsn(settings.redis_url)


async def get_queue() -> ArqRedis:
    """Create an arq Redis pool for enqueuing jobs from the API process."""
    return await create_pool(redis_settings())
