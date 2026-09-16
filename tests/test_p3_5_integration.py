import asyncio
import os
from datetime import datetime, timezone

import pytest

from app.agent.models import AgentPrepared, Intent, ToolEvent
from app.core.config import Settings
from app.observability.metrics import MetricsRegistry
from app.observability.models import LLMUsage
from app.observability.tracing import TraceRecorder
from app.rag.models import Citation
from app.security.rate_limit import RedisFixedWindowRateLimiter
from app.services.backend import BackendService
from app.services.persistence import PostgresRepository
from app.services.session_store import RedisSessionStore


@pytest.mark.skipif(os.getenv("P3_5_INTEGRATION") != "1", reason="requires migrated PostgreSQL and Redis")
def test_migrated_postgres_privacy_retention_and_redis_rate_limit() -> None:
    settings = Settings(
        app_env="test",
        session_backend="redis",
        redis_url=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
        redis_prefix="guilin-ai-p35-ci",
        session_ttl_seconds=300,
        persistence_enabled=True,
        database_url=os.getenv("DATABASE_URL", "postgresql://guilin:guilin@localhost:5432/guilin_ai"),
        database_auto_create=False,
        pii_redaction_enabled=True,
        trace_retention_days=1,
        message_retention_days=1,
        feedback_retention_days=1,
        rate_limit_enabled=True,
        rate_limit_backend="redis",
        rate_limit_requests=2,
        rate_limit_window_seconds=60,
        rate_limit_redis_url=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
    )

    async def scenario() -> None:
        sessions = RedisSessionStore(settings)
        persistence = PostgresRepository(settings)
        backend = BackendService(settings, sessions=sessions, persistence=persistence)
        recorder = TraceRecorder(settings, persistence=persistence, metrics=MetricsRegistry(settings))
        limiter = RedisFixedWindowRateLimiter(settings)
        await backend.startup()
        try:
            await persistence.reset_for_tests()
            session = await backend.create_session()
            trace_id = "tr_p35_integration"
            await backend.append_message(
                session.session_id,
                "user",
                "联系我13800138000，邮箱alice@example.com",
                trace_id=trace_id,
            )
            persisted_message = await persistence._pool().fetchval(
                "SELECT content FROM messages WHERE session_id=$1 ORDER BY id LIMIT 1",
                session.session_id,
            )
            assert "138****8000" in persisted_message
            assert "a***@example.com" in persisted_message
            assert "13800138000" not in persisted_message

            prepared = AgentPrepared(
                intent=Intent.WEATHER,
                grounded=True,
                confidence=0.95,
                context="test evidence",
                gate_reason="tool_evidence",
                tool_calls=[
                    ToolEvent(
                        tool_name="weather",
                        status="success",
                        provider="open_meteo",
                        summary="provider contact 13900139000",
                        attempts=2,
                        latency_ms=123.4,
                        circuit_state="closed",
                    )
                ],
                citations=[
                    Citation(
                        citation_id="C1",
                        document_id="tool:weather:test",
                        chunk_id="weather-test",
                        title="weather evidence",
                        source="Open-Meteo",
                        source_type="tool",
                        tool_name="weather",
                        snippet="contact bob@example.com 13700137000",
                    )
                ],
            )
            trace = recorder.start(
                trace_id,
                session.session_id,
                "身份证110101199001011234，邮箱alice@example.com",
            )
            await recorder.finish(
                trace,
                prepared=prepared,
                status="success",
                usage=LLMUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
            )
            await backend.add_feedback(
                session_id=session.session_id,
                trace_id=trace_id,
                rating="up",
                comment="reply to alice@example.com",
            )

            stored = await persistence.get_trace(trace_id)
            assert stored is not None
            assert "110101********1234" in stored["request_message"]
            assert "a***@example.com" in stored["request_message"]
            assert "139****9000" in stored["tool_calls"][0]["summary"]
            assert "b***@example.com" in stored["citations"][0]["snippet"]
            assert "137****7000" in stored["citations"][0]["snippet"]
            feedback = await persistence._pool().fetchval("SELECT comment FROM feedback LIMIT 1")
            assert "a***@example.com" in feedback

            first = await limiter.check("p35-user")
            second = await limiter.check("p35-user")
            third = await limiter.check("p35-user")
            assert first.allowed and second.allowed and not third.allowed

            await persistence._pool().execute(
                "UPDATE traces SET completed_at = NOW() - INTERVAL '5 days', started_at = NOW() - INTERVAL '5 days'"
            )
            await persistence._pool().execute("UPDATE messages SET created_at = NOW() - INTERVAL '5 days'")
            await persistence._pool().execute("UPDATE feedback SET created_at = NOW() - INTERVAL '5 days'")
            result = await persistence.cleanup_retention(datetime.now(timezone.utc))
            assert result["traces"] >= 1
            assert result["messages"] >= 1
            assert result["feedback"] >= 1
            assert await persistence.get_trace(trace_id) is None
        finally:
            await limiter.close()
            await backend.shutdown()

    asyncio.run(scenario())
