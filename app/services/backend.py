from app.core.config import Settings, get_settings
from app.services.persistence import PostgresRepository, postgres_repository
from app.services.session_store import SessionRecord, SessionStore, session_store


class BackendService:
    """Coordinates short-term session state and durable persistence."""

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        sessions: SessionStore | None = None,
        persistence: PostgresRepository | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.sessions = sessions or session_store
        self.persistence = persistence or postgres_repository

    async def startup(self) -> None:
        await self.persistence.start()

    async def shutdown(self) -> None:
        await self.sessions.close()
        await self.persistence.close()

    async def create_session(self) -> SessionRecord:
        session = await self.sessions.create()
        await self.persistence.ensure_conversation(session)
        return session

    async def get_or_create(self, session_id: str | None) -> SessionRecord:
        session = await self.sessions.get_or_create(session_id)
        await self.persistence.ensure_conversation(session)
        return session

    async def history(self, session_id: str) -> list[dict[str, str]]:
        return await self.sessions.history(session_id)

    async def append_message(
        self,
        session_id: str,
        role: str,
        content: str,
        *,
        trace_id: str | None = None,
    ) -> None:
        await self.sessions.append_message(session_id, role, content)
        await self.persistence.append_message(session_id, role, content, trace_id)

    async def add_feedback(
        self,
        *,
        session_id: str,
        trace_id: str | None,
        rating: str,
        comment: str | None,
    ) -> bool:
        accepted = await self.sessions.add_feedback(
            session_id=session_id,
            trace_id=trace_id,
            rating=rating,
            comment=comment,
        )
        if not accepted:
            return False
        await self.persistence.add_feedback(
            session_id=session_id,
            trace_id=trace_id,
            rating=rating,
            comment=comment,
        )
        return True

    async def dependency_health(self) -> dict[str, bool | str]:
        redis_ok = True
        if self.settings.session_backend.lower() == "redis":
            try:
                redis_ok = await self.sessions.ping()
            except Exception:
                redis_ok = False
        postgres_ok = True
        if self.settings.persistence_enabled:
            postgres_ok = await self.persistence.ping()
        return {
            "session_backend": self.settings.session_backend,
            "redis": redis_ok,
            "persistence_enabled": self.settings.persistence_enabled,
            "postgres": postgres_ok,
        }


backend_service = BackendService()
