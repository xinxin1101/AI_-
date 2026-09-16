from dataclasses import dataclass, field
from datetime import datetime

from app.agent.models import ToolEvent
from app.rag.models import Citation


@dataclass
class LLMUsage:
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None


@dataclass
class TraceRecord:
    trace_id: str
    session_id: str
    request_message: str
    status: str
    intent: str
    grounded: bool
    confidence: float
    gate_reason: str | None
    started_at: datetime
    completed_at: datetime
    latency_ms: float
    llm_model: str
    fallback: bool
    usage: LLMUsage | None = None
    error: str | None = None
    tool_calls: list[ToolEvent] = field(default_factory=list)
    citations: list[Citation] = field(default_factory=list)
