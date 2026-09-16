from enum import StrEnum
from typing import Any, Literal, TypedDict

from pydantic import BaseModel, Field

from app.rag.models import Citation, RAGResult


class Intent(StrEnum):
    KNOWLEDGE = "knowledge"
    WEATHER = "realtime_weather"
    SCENIC_INFO = "scenic_info"
    ROUTE = "route"
    ITINERARY = "itinerary"


class ToolEvidence(BaseModel):
    evidence_id: str
    tool_name: str
    title: str
    content: str
    source: str
    source_url: str | None = None
    observed_at: str | None = None
    freshness_class: str = "realtime"
    confidence: float = Field(default=0.95, ge=0.0, le=1.0)
    citable: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)


class ToolEvent(BaseModel):
    tool_name: str
    status: Literal["success", "error", "skipped"]
    provider: str
    summary: str


class AgentPrepared(BaseModel):
    intent: Intent
    grounded: bool
    confidence: float = Field(ge=0.0, le=1.0)
    context: str = ""
    citations: list[Citation] = Field(default_factory=list)
    tool_calls: list[ToolEvent] = Field(default_factory=list)
    gate_reason: str | None = None
    fallback_answer: str = ""

    @property
    def can_generate(self) -> bool:
        return self.grounded and bool(self.context.strip())


class AgentState(TypedDict, total=False):
    query: str
    history: list[dict[str, str]]
    rag_result: RAGResult
    intent: str
    tool_evidence: list[ToolEvidence]
    tool_calls: list[ToolEvent]
    context: str
    citations: list[Citation]
    grounded: bool
    confidence: float
    gate_reason: str | None
    fallback_answer: str
