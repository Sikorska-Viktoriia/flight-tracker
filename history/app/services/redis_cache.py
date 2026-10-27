from redis.asyncio import Redis

from history.app.config.settings import Settings
from history.app.interfaces.cache import Cache


class RedisCache(Cache):
    def __init__(self, redis: Redis) -> None:
        self.redis = redis

    @classmethod
    def from_settings(cls, settings: Settings) -> "RedisCache":
        return cls(Redis.from_url(settings.redis_url, decode_responses=True))

    async def get(self, key: str) -> str | None:
        return await self.redis.get(key)

    async def set(self, key: str, value: str, ex: int) -> None:
        await self.redis.set(key, value, ex=ex)

    async def delete(self, key: str) -> None:
        await self.redis.delete(key)

    async def ping(self) -> bool:
        return bool(await self.redis.ping())

    async def aclose(self) -> None:
        await self.redis.aclose()
