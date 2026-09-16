import asyncio
import os

from app.agent.models import AgentPrepared, Intent, ToolEvent
from app.core.config import Settings
from app.observability.metrics import MetricsRegistry
from app.observability.models import LLMUsage
from app.observability.tracing import TraceRecorder
from app.services.backend import BackendService
from app.services.persistence import PostgresRepository
from app.services.session_store import RedisSessionStore


def test_real_redis_and_postgres_round_trip() -> None:
    settings = Settings(
        app_env="test",
        session_backend="redis",
        redis_url=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
        redis_prefix="guilin-ai-ci",
        session_ttl_seconds=300,
        persistence_enabled=True,
        database_url=os.getenv(
            "DATABASE_URL",
            "postgresql://guilin:guilin@localhost:5432/guilin_ai",
        ),
        database_auto_create=True,
        metrics_window_size=100,
    )

    async def scenario() -> None:
        sessions = RedisSessionStore(settings)
        persistence = PostgresRepository(settings)
        backend = BackendService(settings, sessions=sessions, persistence=persistence)
        recorder = TraceRecorder(
            settings,
            persistence=persistence,
            metrics=MetricsRegistry(settings),
        )
        await backend.startup()
        try:
            await persistence.reset_for_tests()
            assert await sessions.ping() is True
            assert await persistence.ping() is True

            session = await backend.create_session()
            trace_id = "tr_p3_integration"
            await backend.append_message(
                session.session_id,
                "user",
                "明天桂林天气怎么样？",
                trace_id=trace_id,
            )
            await backend.append_message(
                session.session_id,
                "assistant",
                "测试回答",
                trace_id=trace_id,
            )
            history = await backend.history(session.session_id)
            assert [item["role"] for item in history] == ["user", "assistant"]

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
                        summary="weather evidence",
                        attempts=2,
                        latency_ms=123.4,
                        circuit_state="closed",
                    )
                ],
            )
            trace = recorder.start(trace_id, session.session_id, "明天桂林天气怎么样？")
            await recorder.finish(
                trace,
                prepared=prepared,
                status="success",
                usage=LLMUsage(prompt_tokens=100, completion_tokens=20, total_tokens=120),
            )
            accepted = await backend.add_feedback(
                session_id=session.session_id,
                trace_id=trace_id,
                rating="up",
                comment="useful",
            )
            assert accepted is True

            stored = await persistence.get_trace(trace_id)
            assert stored is not None
            assert stored["intent"] == "realtime_weather"
            assert stored["total_tokens"] == 120
            assert stored["tool_calls"][0]["attempts"] == 2
            assert stored["tool_calls"][0]["circuit_state"] == "closed"
        finally:
            await backend.shutdown()

    asyncio.run(scenario())
