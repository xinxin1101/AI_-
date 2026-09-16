from dataclasses import dataclass
from datetime import datetime, timezone
from time import perf_counter

from app.agent.models import AgentPrepared
from app.core.config import Settings, get_settings
from app.observability.metrics import MetricsRegistry, metrics_registry
from app.observability.models import LLMUsage, TraceRecord
from app.observability.otel import telemetry_runtime
from app.services.persistence import PostgresRepository, postgres_repository


@dataclass
class TraceContext:
    trace_id: str
    session_id: str
    request_message: str
    started_at: datetime
    started_monotonic: float


class TraceRecorder:
    def __init__(
        self,
        settings: Settings | None = None,
        *,
        persistence: PostgresRepository | None = None,
        metrics: MetricsRegistry | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.persistence = persistence or postgres_repository
        self.metrics = metrics or metrics_registry

    def start(self, trace_id: str, session_id: str, request_message: str) -> TraceContext:
        telemetry_runtime.annotate_current_span(app_trace_id=trace_id, session_id=session_id)
        return TraceContext(
            trace_id=trace_id,
            session_id=session_id,
            request_message=request_message,
            started_at=datetime.now(timezone.utc),
            started_monotonic=perf_counter(),
        )

    async def finish(
        self,
        context: TraceContext,
        *,
        prepared: AgentPrepared | None,
        status: str,
        usage: LLMUsage | None = None,
        error: str | None = None,
    ) -> TraceRecord:
        completed_at = datetime.now(timezone.utc)
        record = TraceRecord(
            trace_id=context.trace_id,
            session_id=context.session_id,
            request_message=context.request_message,
            status=status,
            intent=prepared.intent.value if prepared else "unknown",
            grounded=prepared.grounded if prepared else False,
            confidence=prepared.confidence if prepared else 0.0,
            gate_reason=prepared.gate_reason if prepared else None,
            started_at=context.started_at,
            completed_at=completed_at,
            latency_ms=round((perf_counter() - context.started_monotonic) * 1000, 3),
            llm_model=self.settings.llm_model,
            fallback=not prepared.can_generate if prepared else True,
            usage=usage,
            error=error,
            tool_calls=list(prepared.tool_calls) if prepared else [],
            citations=list(prepared.citations) if prepared else [],
        )
        telemetry_runtime.annotate_current_span(
            intent=record.intent,
            grounded=record.grounded,
            fallback=record.fallback,
            status=record.status,
            tool_call_count=len(record.tool_calls),
            citation_count=len(record.citations),
            latency_ms=record.latency_ms,
            total_tokens=record.usage.total_tokens if record.usage else None,
        )
        await self.persistence.persist_trace(record)
        await self.metrics.observe(record)
        return record


trace_recorder = TraceRecorder()
