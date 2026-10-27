import asyncpg

from history.app.config.settings import Settings
from history.app.interfaces.cache import Cache
from history.app.services.postgres_cache import PostgresCache
from history.app.services.redis_cache import RedisCache


def create_cache(settings: Settings, pool: asyncpg.Pool) -> Cache:
    if settings.uses_postgres_cache:
        return PostgresCache(pool)
    return RedisCache.from_settings(settings)
