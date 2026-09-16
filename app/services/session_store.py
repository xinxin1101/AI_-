import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Protocol
from uuid import uuid4

from redis.asyncio import Redis

from app.core.config import Settings, get_settings


@dataclass
class SessionRecord:
    session_id: str
    created_at: datetime
    messages: list[dict[str, str]] = field(default_factory=list)


class SessionStore(Protocol):
    async def create(self) -> SessionRecord: ...
    async def get(self, session_id: str) -> SessionRecord | None: ...
    async def get_or_create(self, session_id: str | None) -> SessionRecord: ...
    async def history(self, session_id: str) -> list[dict[str, str]]: ...
    async def append_message(self, session_id: str, role: str, content: str) -> None: ...
    async def add_feedback(
        self,
        *,
        session_id: str,
        trace_id: str | None,
        rating: str,
        comment: str | None,
    ) -> bool: ...
    async def ping(self) -> bool: ...
    async def close(self) -> None: ...


class InMemorySessionStore:
    def __init__(self, settings: Settings | None = None) -> None:
        self._sessions: dict[str, SessionRecord] = {}
        self._feedback: list[dict[str, str | None]] = []
        self._lock = asyncio.Lock()
        self._settings = settings or get_settings()

    async def create(self) -> SessionRecord:
        record = SessionRecord(
            session_id=f"sess_{uuid4().hex}",
            created_at=datetime.now(timezone.utc),
        )
        async with self._lock:
            self._sessions[record.session_id] = record
        return record

    async def get(self, session_id: str) -> SessionRecord | None:
        async with self._lock:
            return self._sessions.get(session_id)

    async def get_or_create(self, session_id: str | None) -> SessionRecord:
        if session_id:
            record = await self.get(session_id)
            if record is not None:
                return record
        return await self.create()

    async def history(self, session_id: str) -> list[dict[str, str]]:
        async with self._lock:
            record = self._sessions[session_id]
            return [message.copy() for message in record.messages]

    async def append_message(self, session_id: str, role: str, content: str) -> None:
        async with self._lock:
            record = self._sessions[session_id]
            record.messages.append({"role": role, "content": content})
            overflow = len(record.messages) - self._settings.session_max_messages
            if overflow > 0:
                del record.messages[:overflow]

    async def add_feedback(
        self,
        *,
        session_id: str,
        trace_id: str | None,
        rating: str,
        comment: str | None,
    ) -> bool:
        async with self._lock:
            if session_id not in self._sessions:
                return False
            self._feedback.append(
                {
                    "session_id": session_id,
                    "trace_id": trace_id,
                    "rating": rating,
                    "comment": comment,
                }
            )
            return True

    async def ping(self) -> bool:
        return True

    async def close(self) -> None:
        return None


class RedisSessionStore:
    """Redis-backed short-term conversation window with sliding TTL."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.redis = Redis.from_url(
            self.settings.redis_url,
            decode_responses=True,
            socket_timeout=self.settings.redis_socket_timeout_seconds,
        )

    def _meta_key(self, session_id: str) -> str:
        return f"{self.settings.redis_prefix}:session:{session_id}:meta"

    def _messages_key(self, session_id: str) -> str:
        return f"{self.settings.redis_prefix}:session:{session_id}:messages"

    async def create(self) -> SessionRecord:
        record = SessionRecord(
            session_id=f"sess_{uuid4().hex}",
            created_at=datetime.now(timezone.utc),
        )
        ttl = self.settings.session_ttl_seconds
        async with self.redis.pipeline(transaction=True) as pipe:
            pipe.hset(
                self._meta_key(record.session_id),
                mapping={"created_at": record.created_at.isoformat()},
            )
            pipe.expire(self._meta_key(record.session_id), ttl)
            await pipe.execute()
        return record

    async def get(self, session_id: str) -> SessionRecord | None:
        payload = await self.redis.hgetall(self._meta_key(session_id))
        if not payload:
            return None
        created_at = datetime.fromisoformat(payload["created_at"])
        return SessionRecord(
            session_id=session_id,
            created_at=created_at,
            messages=await self.history(session_id),
        )

    async def get_or_create(self, session_id: str | None) -> SessionRecord:
        if session_id:
            record = await self.get(session_id)
            if record is not None:
                await self._touch(session_id)
                return record
        return await self.create()

    async def history(self, session_id: str) -> list[dict[str, str]]:
        raw = await self.redis.lrange(self._messages_key(session_id), 0, -1)
        result: list[dict[str, str]] = []
        for item in raw:
            try:
                parsed = json.loads(item)
            except json.JSONDecodeError:
                continue
            if (
                isinstance(parsed, dict)
                and isinstance(parsed.get("role"), str)
                and isinstance(parsed.get("content"), str)
            ):
                result.append({"role": parsed["role"], "content": parsed["content"]})
        return result

    async def append_message(self, session_id: str, role: str, content: str) -> None:
        message = json.dumps({"role": role, "content": content}, ensure_ascii=False)
        key = self._messages_key(session_id)
        ttl = self.settings.session_ttl_seconds
        async with self.redis.pipeline(transaction=True) as pipe:
            pipe.rpush(key, message)
            pipe.ltrim(key, -self.settings.session_max_messages, -1)
            pipe.expire(key, ttl)
            pipe.expire(self._meta_key(session_id), ttl)
            await pipe.execute()

    async def add_feedback(
        self,
        *,
        session_id: str,
        trace_id: str | None,
        rating: str,
        comment: str | None,
    ) -> bool:
        return bool(await self.redis.exists(self._meta_key(session_id)))

    async def _touch(self, session_id: str) -> None:
        ttl = self.settings.session_ttl_seconds
        async with self.redis.pipeline(transaction=True) as pipe:
            pipe.expire(self._meta_key(session_id), ttl)
            pipe.expire(self._messages_key(session_id), ttl)
            await pipe.execute()

    async def ping(self) -> bool:
        return bool(await self.redis.ping())

    async def close(self) -> None:
        await self.redis.aclose()


def create_session_store(settings: Settings | None = None) -> SessionStore:
    settings = settings or get_settings()
    backend = settings.session_backend.strip().lower()
    if backend == "memory":
        return InMemorySessionStore(settings)
    if backend == "redis":
        return RedisSessionStore(settings)
    raise ValueError(f"Unsupported SESSION_BACKEND: {settings.session_backend}")


session_store = create_session_store()
