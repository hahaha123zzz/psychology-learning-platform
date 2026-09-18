import hashlib

import redis.asyncio as redis

from app.core.config import get_settings


class LoginRateLimiter:
    """按账号与IP组合限流连续登录失败。"""

    def __init__(self, client: redis.Redis) -> None:
        self._client = client
        self._settings = get_settings()

    @staticmethod
    def _key(email: str, ip: str) -> str:
        digest = hashlib.sha256(email.strip().lower().encode("utf-8")).hexdigest()[:24]
        return f"login_fail:{digest}:{ip}"

    async def is_blocked(self, email: str, ip: str) -> bool:
        count = await self._client.get(self._key(email, ip))
        limit = self._settings.login_fail_limit
        return count is not None and int(count) >= limit

    async def record_failure(self, email: str, ip: str) -> int:
        key = self._key(email, ip)
        async with self._client.pipeline(transaction=True) as pipe:
            pipe.incr(key)
            pipe.expire(key, self._settings.login_fail_window_seconds)
            count, _ = await pipe.execute()
        return int(count)

    async def clear(self, email: str, ip: str) -> None:
        await self._client.delete(self._key(email, ip))
