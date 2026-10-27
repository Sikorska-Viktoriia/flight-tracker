import asyncpg

from history.app.interfaces.cache import Cache


class PostgresCache(Cache):
    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool

    async def get(self, key: str) -> str | None:
        return await self.pool.fetchval(
            """
            SELECT value
            FROM app_cache
            WHERE cache_key = $1 AND expires_at > NOW()
            """,
            key,
        )

    async def set(self, key: str, value: str, ex: int) -> None:
        await self.pool.execute("DELETE FROM app_cache WHERE expires_at <= NOW()")
        await self.pool.execute(
            """
            INSERT INTO app_cache (cache_key, value, expires_at)
            VALUES ($1, $2, NOW() + $3::int * INTERVAL '1 second')
            ON CONFLICT (cache_key) DO UPDATE
            SET value = EXCLUDED.value, expires_at = EXCLUDED.expires_at
            """,
            key,
            value,
            ex,
        )

    async def delete(self, key: str) -> None:
        await self.pool.execute("DELETE FROM app_cache WHERE cache_key = $1", key)

    async def ping(self) -> bool:
        return await self.pool.fetchval("SELECT 1") == 1

    async def aclose(self) -> None:
        return None
