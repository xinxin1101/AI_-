from __future__ import annotations

import asyncio
import hashlib
import hmac
import time
from dataclasses import dataclass

from redis.asyncio import Redis

from app.core.config import Settings, get_settings


@dataclass
class RateLimitDecision:
    allowed: bool
    limit: int
    remaining: int
    reset_after_seconds: int


class APIKeyAuthenticator:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def verify(self, candidate: str | None) -> bool:
        if not self.settings.api_auth_enabled:
            return True
        if not candidate:
            return False
        keys = self.settings.api_key_list
        if not keys:
            return False
        return any(hmac.compare_digest(candidate, configured) for configured in keys)

    @staticmethod
    def identity(candidate: str | None, client_host: str | None) -> str:
        raw = candidate or client_host or "anonymous"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


class MemoryFixedWindowRateLimiter:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._lock = asyncio.Lock()
        self._counts: dict[tuple[str, int], int] = {}

    async def check(self, identity: str) -> RateLimitDecision:
        now = int(time.time())
        window = self.settings.rate_limit_window_seconds
        bucket = now // window
        key = (identity, bucket)
        async with self._lock:
            self._counts[key] = self._counts.get(key, 0) + 1
            count = self._counts[key]
            for stale in [item for item in self._counts if item[1] < bucket - 1]:
                self._counts.pop(stale, None)
        limit = self.settings.rate_limit_requests
        reset = window - (now % window)
        return RateLimitDecision(
            allowed=count <= limit,
            limit=limit,
            remaining=max(0, limit - count),
            reset_after_seconds=max(1, reset),
        )

    async def close(self) -> None:
        return None


class RedisFixedWindowRateLimiter:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        url = self.settings.rate_limit_redis_url or self.settings.redis_url
        self.redis = Redis.from_url(
            url,
            decode_responses=True,
            socket_timeout=self.settings.redis_socket_timeout_seconds,
        )

    async def check(self, identity: str) -> RateLimitDecision:
        now = int(time.time())
        window = self.settings.rate_limit_window_seconds
        bucket = now // window
        key = f"{self.settings.redis_prefix}:rate:{identity}:{bucket}"
        async with self.redis.pipeline(transaction=True) as pipe:
            pipe.incr(key)
            pipe.expire(key, window + 2)
            count, _ = await pipe.execute()
        limit = self.settings.rate_limit_requests
        reset = window - (now % window)
        return RateLimitDecision(
            allowed=int(count) <= limit,
            limit=limit,
            remaining=max(0, limit - int(count)),
            reset_after_seconds=max(1, reset),
        )

    async def close(self) -> None:
        await self.redis.aclose()


class SecurityService:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.auth = APIKeyAuthenticator(self.settings)
        self.limiter: MemoryFixedWindowRateLimiter | RedisFixedWindowRateLimiter | None = None

    async def startup(self) -> None:
        if self.settings.api_auth_enabled and not self.settings.api_key_list:
            raise RuntimeError("API_AUTH_ENABLED=true requires at least one API_KEYS value")
        if not self.settings.rate_limit_enabled:
            return
        if self.settings.rate_limit_backend.lower() == "redis":
            self.limiter = RedisFixedWindowRateLimiter(self.settings)
        else:
            self.limiter = MemoryFixedWindowRateLimiter(self.settings)

    async def shutdown(self) -> None:
        if self.limiter is not None:
            await self.limiter.close()
            self.limiter = None

    async def rate_limit(self, identity: str) -> RateLimitDecision | None:
        if not self.settings.rate_limit_enabled:
            return None
        if self.limiter is None:
            raise RuntimeError("rate limiter is not started")
        return await self.limiter.check(identity)


security_service = SecurityService()
