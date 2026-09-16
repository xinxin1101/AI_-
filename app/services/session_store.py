import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4

from app.core.config import get_settings


@dataclass
class SessionRecord:
    session_id: str
    created_at: datetime
    messages: list[dict[str, str]] = field(default_factory=list)


class InMemorySessionStore:
    """P0 process-local store. Replace with Redis/PostgreSQL in a later phase."""

    def __init__(self) -> None:
        self._sessions: dict[str, SessionRecord] = {}
        self._feedback: list[dict[str, str | None]] = []
        self._lock = asyncio.Lock()
        self._settings = get_settings()

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


session_store = InMemorySessionStore()
