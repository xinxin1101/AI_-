from __future__ import annotations

from datetime import datetime, timedelta, timezone

import asyncpg

from app.core.config import Settings, get_settings
from app.observability.models import TraceRecord
from app.security.privacy import PrivacyRedactor
from app.services.session_store import SessionRecord


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS conversations (
    session_id TEXT PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS messages (
    id BIGSERIAL PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES conversations(session_id) ON DELETE CASCADE,
    trace_id TEXT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_messages_session_created ON messages(session_id, created_at);
CREATE TABLE IF NOT EXISTS traces (
    trace_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES conversations(session_id) ON DELETE CASCADE,
    request_message TEXT NOT NULL,
    status TEXT NOT NULL,
    intent TEXT NOT NULL,
    grounded BOOLEAN NOT NULL,
    confidence DOUBLE PRECISION NOT NULL,
    gate_reason TEXT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ NOT NULL,
    latency_ms DOUBLE PRECISION NOT NULL,
    llm_model TEXT NOT NULL,
    prompt_tokens INTEGER NULL,
    completion_tokens INTEGER NULL,
    total_tokens INTEGER NULL,
    fallback BOOLEAN NOT NULL DEFAULT FALSE,
    error TEXT NULL
);
CREATE INDEX IF NOT EXISTS idx_traces_session_started ON traces(session_id, started_at DESC);
CREATE TABLE IF NOT EXISTS tool_calls (
    id BIGSERIAL PRIMARY KEY,
    trace_id TEXT NOT NULL REFERENCES traces(trace_id) ON DELETE CASCADE,
    tool_name TEXT NOT NULL,
    status TEXT NOT NULL,
    provider TEXT NOT NULL,
    summary TEXT NOT NULL,
    attempts INTEGER NULL,
    latency_ms DOUBLE PRECISION NULL,
    circuit_state TEXT NULL
);
CREATE INDEX IF NOT EXISTS idx_tool_calls_trace ON tool_calls(trace_id);
CREATE TABLE IF NOT EXISTS citations (
    id BIGSERIAL PRIMARY KEY,
    trace_id TEXT NOT NULL REFERENCES traces(trace_id) ON DELETE CASCADE,
    citation_id TEXT NOT NULL,
    document_id TEXT NOT NULL,
    chunk_id TEXT NOT NULL,
    title TEXT NOT NULL,
    source TEXT NOT NULL,
    source_url TEXT NULL,
    source_type TEXT NOT NULL,
    tool_name TEXT NULL,
    updated_at TEXT NULL,
    observed_at TEXT NULL,
    snippet TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_citations_trace ON citations(trace_id);
CREATE TABLE IF NOT EXISTS feedback (
    id BIGSERIAL PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES conversations(session_id) ON DELETE CASCADE,
    trace_id TEXT NULL,
    rating TEXT NOT NULL,
    comment TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_feedback_session_created ON feedback(session_id, created_at DESC);
"""


class PostgresRepository:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.pool: asyncpg.Pool | None = None
        self.redactor = PrivacyRedactor(self.settings)

    async def start(self) -> None:
        if not self.settings.persistence_enabled or self.pool is not None:
            return
        self.pool = await asyncpg.create_pool(
            dsn=self.settings.database_url,
            min_size=self.settings.database_min_pool_size,
            max_size=self.settings.database_max_pool_size,
            command_timeout=self.settings.database_command_timeout_seconds,
        )
        if self.settings.database_auto_create:
            async with self.pool.acquire() as conn:
                await conn.execute(SCHEMA_SQL)

    async def close(self) -> None:
        if self.pool is not None:
            await self.pool.close()
            self.pool = None

    async def ping(self) -> bool:
        if not self.settings.persistence_enabled:
            return True
        if self.pool is None:
            return False
        try:
            async with self.pool.acquire() as conn:
                return bool(await conn.fetchval("SELECT TRUE"))
        except Exception:
            return False

    async def ensure_conversation(self, session: SessionRecord) -> None:
        if not self.settings.persistence_enabled:
            return
        await self._pool().execute(
            """INSERT INTO conversations(session_id, created_at, updated_at)
            VALUES($1, $2, NOW())
            ON CONFLICT(session_id) DO UPDATE SET updated_at = NOW()""",
            session.session_id,
            session.created_at,
        )

    async def append_message(self, session_id: str, role: str, content: str, trace_id: str | None = None) -> None:
        if not self.settings.persistence_enabled:
            return
        pool = self._pool()
        await pool.execute(
            "INSERT INTO messages(session_id, trace_id, role, content) VALUES($1, $2, $3, $4)",
            session_id,
            trace_id,
            role,
            self.redactor.text(content) or "",
        )
        await pool.execute("UPDATE conversations SET updated_at = NOW() WHERE session_id = $1", session_id)

    async def add_feedback(self, *, session_id: str, trace_id: str | None, rating: str, comment: str | None) -> None:
        if not self.settings.persistence_enabled:
            return
        await self._pool().execute(
            "INSERT INTO feedback(session_id, trace_id, rating, comment) VALUES($1, $2, $3, $4)",
            session_id,
            trace_id,
            rating,
            self.redactor.text(comment),
        )

    async def persist_trace(self, record: TraceRecord) -> None:
        if not self.settings.persistence_enabled:
            return
        usage = record.usage
        async with self._pool().acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    """INSERT INTO traces(
                        trace_id, session_id, request_message, status, intent,
                        grounded, confidence, gate_reason, started_at, completed_at,
                        latency_ms, llm_model, prompt_tokens, completion_tokens,
                        total_tokens, fallback, error
                    ) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17)
                    ON CONFLICT(trace_id) DO NOTHING""",
                    record.trace_id,
                    record.session_id,
                    self.redactor.text(record.request_message) or "",
                    record.status,
                    record.intent,
                    record.grounded,
                    record.confidence,
                    record.gate_reason,
                    record.started_at,
                    record.completed_at,
                    record.latency_ms,
                    record.llm_model,
                    usage.prompt_tokens if usage else None,
                    usage.completion_tokens if usage else None,
                    usage.total_tokens if usage else None,
                    record.fallback,
                    self.redactor.text(record.error),
                )
                for tool in record.tool_calls:
                    await conn.execute(
                        """INSERT INTO tool_calls(
                            trace_id, tool_name, status, provider, summary, attempts, latency_ms, circuit_state
                        ) VALUES($1,$2,$3,$4,$5,$6,$7,$8)""",
                        record.trace_id,
                        tool.tool_name,
                        tool.status,
                        tool.provider,
                        self.redactor.text(tool.summary) or "",
                        tool.attempts,
                        tool.latency_ms,
                        tool.circuit_state,
                    )
                for citation in record.citations:
                    await conn.execute(
                        """INSERT INTO citations(
                            trace_id, citation_id, document_id, chunk_id, title, source, source_url,
                            source_type, tool_name, updated_at, observed_at, snippet
                        ) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12)""",
                        record.trace_id,
                        citation.citation_id,
                        citation.document_id,
                        citation.chunk_id,
                        citation.title,
                        citation.source,
                        self.redactor.text(citation.source_url),
                        citation.source_type,
                        citation.tool_name,
                        citation.updated_at,
                        citation.observed_at,
                        self.redactor.text(citation.snippet) or "",
                    )

    async def get_trace(self, trace_id: str) -> dict | None:
        if not self.settings.persistence_enabled:
            return None
        pool = self._pool()
        row = await pool.fetchrow("SELECT * FROM traces WHERE trace_id = $1", trace_id)
        if row is None:
            return None
        tools = await pool.fetch("SELECT * FROM tool_calls WHERE trace_id = $1 ORDER BY id", trace_id)
        citations = await pool.fetch("SELECT * FROM citations WHERE trace_id = $1 ORDER BY id", trace_id)
        result = dict(row)
        result["tool_calls"] = [dict(item) for item in tools]
        result["citations"] = [dict(item) for item in citations]
        return result

    async def cleanup_retention(self, now: datetime | None = None) -> dict[str, int]:
        if not self.settings.persistence_enabled:
            return {"traces": 0, "messages": 0, "feedback": 0, "conversations": 0}
        now = now or datetime.now(timezone.utc)
        trace_cutoff = now - timedelta(days=self.settings.trace_retention_days)
        message_cutoff = now - timedelta(days=self.settings.message_retention_days)
        feedback_cutoff = now - timedelta(days=self.settings.feedback_retention_days)
        async with self._pool().acquire() as conn:
            async with conn.transaction():
                traces = self._command_count(await conn.execute("DELETE FROM traces WHERE completed_at < $1", trace_cutoff))
                messages = self._command_count(await conn.execute("DELETE FROM messages WHERE created_at < $1", message_cutoff))
                feedback = self._command_count(await conn.execute("DELETE FROM feedback WHERE created_at < $1", feedback_cutoff))
                conversations = self._command_count(
                    await conn.execute(
                        """DELETE FROM conversations c
                        WHERE NOT EXISTS (SELECT 1 FROM messages m WHERE m.session_id = c.session_id)
                          AND NOT EXISTS (SELECT 1 FROM traces t WHERE t.session_id = c.session_id)
                          AND NOT EXISTS (SELECT 1 FROM feedback f WHERE f.session_id = c.session_id)"""
                    )
                )
        return {"traces": traces, "messages": messages, "feedback": feedback, "conversations": conversations}

    async def reset_for_tests(self) -> None:
        if self.settings.app_env != "test":
            raise RuntimeError("reset_for_tests is only allowed in APP_ENV=test")
        if not self.settings.persistence_enabled:
            return
        await self._pool().execute(
            "TRUNCATE feedback, citations, tool_calls, traces, messages, conversations RESTART IDENTITY CASCADE"
        )

    @staticmethod
    def _command_count(status: str) -> int:
        try:
            return int(status.rsplit(" ", 1)[-1])
        except (TypeError, ValueError):
            return 0

    def _pool(self) -> asyncpg.Pool:
        if self.pool is None:
            raise RuntimeError("PostgreSQL persistence is not started")
        return self.pool


postgres_repository = PostgresRepository()
