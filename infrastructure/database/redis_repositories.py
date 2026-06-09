from typing import Dict, List, Optional, Tuple

from redis.asyncio import Redis

from core.repositories import IRedisRepository


class RedisRepository(IRedisRepository):
    def __init__(self, client: Redis):
        self._client = client

    async def set_hash(
        self, key: str, fields: dict, ttl_seconds: Optional[int] = None
    ) -> bool:
        async with self._client.pipeline(transaction=True) as pipe:
            pipe.hset(key, mapping=fields)
            if ttl_seconds is not None:
                pipe.expire(key, ttl_seconds)
            result = await pipe.execute()
        return result[0] >= 0

    async def get(self, key: str) -> Optional[Dict]:
        data = await self._client.hgetall(key)
        return data if data else None

    async def delete(self, key: str) -> bool:
        deleted = await self._client.delete(key)
        return deleted > 0

    async def scan_all(self, key_prefix: str) -> List[Tuple[str, Dict]]:
        keys = []
        async for key in self._client.scan_iter(f"{key_prefix}*"):
            keys.append(key)
        if not keys:
            return []
        async with self._client.pipeline(transaction=False) as pipe:
            for key in keys:
                pipe.hgetall(key)
            results = await pipe.execute()

        return [
            (key.removeprefix(key_prefix), data)
            for key, data in zip(keys, results)
            if data
        ]

    async def queue_push(self, key: str, raw: str) -> bool:
        pushed = await self._client.rpush(key, raw)
        return pushed > 0

    async def queue_pop(
        self, key: str, timeout: int = 10
    ) -> Optional[str | bytes]:
        result = await self._client.blpop(key, timeout=timeout)
        if result is None:
            return None
        _, raw = result
        return raw

    async def queue_length(self, key: str) -> int:
        return await self._client.llen(key)

    async def queue_clear(self, key: str) -> bool:
        is_deleted = await self._client.delete(key)
        return is_deleted > 0
