import asyncio
from collections import Counter, deque
from dataclasses import dataclass
from math import ceil

from app.core.config import Settings, get_settings
from app.observability.models import TraceRecord


@dataclass
class _MetricTrace:
    latency_ms: float
    intent: str
    fallback: bool
    total_tokens: int | None
    tool_successes: int
    tool_total: int
    tool_retries: int
    circuit_open: int


class MetricsRegistry:
    """Bounded process-local metrics window; durable traces live in PostgreSQL."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._items: deque[_MetricTrace] = deque(maxlen=self.settings.metrics_window_size)
        self._lock = asyncio.Lock()

    async def observe(self, record: TraceRecord) -> None:
        tool_total = len(record.tool_calls)
        item = _MetricTrace(
            latency_ms=record.latency_ms,
            intent=record.intent,
            fallback=record.fallback,
            total_tokens=record.usage.total_tokens if record.usage else None,
            tool_successes=sum(1 for tool in record.tool_calls if tool.status == "success"),
            tool_total=tool_total,
            tool_retries=sum(1 for tool in record.tool_calls if (tool.attempts or 1) > 1),
            circuit_open=sum(1 for tool in record.tool_calls if tool.circuit_state == "open"),
        )
        async with self._lock:
            self._items.append(item)

    @staticmethod
    def _percentile(values: list[float], p: float) -> float:
        if not values:
            return 0.0
        ordered = sorted(values)
        index = max(0, min(len(ordered) - 1, ceil(p * len(ordered)) - 1))
        return round(ordered[index], 3)

    async def summary(self) -> dict:
        async with self._lock:
            items = list(self._items)
        count = len(items)
        tool_total = sum(item.tool_total for item in items)
        known_tokens = [item.total_tokens for item in items if item.total_tokens is not None]
        intents = Counter(item.intent for item in items)
        return {
            "window_size": count,
            "latency_ms": {
                "p50": self._percentile([item.latency_ms for item in items], 0.50),
                "p95": self._percentile([item.latency_ms for item in items], 0.95),
            },
            "tokens": {"known_trace_count": len(known_tokens), "total": sum(known_tokens)},
            "tool_success_rate": (
                round(sum(item.tool_successes for item in items) / tool_total, 4)
                if tool_total else None
            ),
            "retry_rate": (
                round(sum(item.tool_retries for item in items) / tool_total, 4)
                if tool_total else None
            ),
            "circuit_open_rate": (
                round(sum(item.circuit_open for item in items) / tool_total, 4)
                if tool_total else None
            ),
            "fallback_rate": (
                round(sum(item.fallback for item in items) / count, 4) if count else 0.0
            ),
            "intent_distribution": dict(sorted(intents.items())),
        }

    async def prometheus_text(self) -> str:
        summary = await self.summary()
        lines = [
            "# TYPE guilin_ai_trace_window_size gauge",
            f"guilin_ai_trace_window_size {summary['window_size']}",
            "# TYPE guilin_ai_latency_p50_ms gauge",
            f"guilin_ai_latency_p50_ms {summary['latency_ms']['p50']}",
            "# TYPE guilin_ai_latency_p95_ms gauge",
            f"guilin_ai_latency_p95_ms {summary['latency_ms']['p95']}",
            "# TYPE guilin_ai_fallback_rate gauge",
            f"guilin_ai_fallback_rate {summary['fallback_rate']}",
            "# TYPE guilin_ai_tokens_total gauge",
            f"guilin_ai_tokens_total {summary['tokens']['total']}",
        ]
        for name in ("tool_success_rate", "retry_rate", "circuit_open_rate"):
            value = summary[name]
            if value is not None:
                lines.extend([f"# TYPE guilin_ai_{name} gauge", f"guilin_ai_{name} {value}"])
        for intent, value in summary["intent_distribution"].items():
            lines.append(f'guilin_ai_intent_count{{intent="{intent}"}} {value}')
        return "\n".join(lines) + "\n"


metrics_registry = MetricsRegistry()
