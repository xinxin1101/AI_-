from pydantic import BaseModel, Field


class RAGEvalCase(BaseModel):
    case_id: str
    query: str
    expected_document_ids: list[str] = Field(default_factory=list)
    expected_terms: list[str] = Field(default_factory=list)
    should_ground: bool = True
    category: str = "general"


class RAGEvalCaseResult(BaseModel):
    case_id: str
    should_ground: bool
    grounded: bool
    expected_document_ids: list[str]
    retrieved_document_ids: list[str]
    reciprocal_rank: float
    recall_at_5: float
    citation_hit: float
    evidence_coverage: float
    gate_reason: str | None = None


class RAGEvalReport(BaseModel):
    case_count: int
    positive_case_count: int
    recall_at_5: float
    mrr: float
    grounding_accuracy: float
    citation_hit_rate: float
    evidence_coverage: float
    passed: bool
    thresholds: dict[str, float]
    cases: list[RAGEvalCaseResult]
