from pydantic import BaseModel, Field


class KnowledgeDocument(BaseModel):
    document_id: str = Field(min_length=1, max_length=200)
    title: str = Field(min_length=1, max_length=300)
    content: str = Field(min_length=1)
    category: str = "general"
    source: str = "unknown"
    source_url: str | None = None
    updated_at: str | None = None
    tags: list[str] = Field(default_factory=list)
    source_id: str | None = None
    publisher: str | None = None
    authority_level: str = "unknown"
    freshness_class: str = "static"
    source_verified_at: str | None = None
    expires_at: str | None = None
    content_hash: str | None = None


class KnowledgeChunk(BaseModel):
    chunk_id: str
    document_id: str
    title: str
    text: str
    category: str
    source: str
    source_url: str | None = None
    updated_at: str | None = None
    tags: list[str] = Field(default_factory=list)
    source_id: str | None = None
    publisher: str | None = None
    authority_level: str = "unknown"
    freshness_class: str = "static"
    source_verified_at: str | None = None
    expires_at: str | None = None
    content_hash: str | None = None


class RetrievalHit(BaseModel):
    chunk: KnowledgeChunk
    dense_score: float = 0.0
    bm25_score: float = 0.0
    rrf_score: float = 0.0
    rerank_score: float = 0.0


class Citation(BaseModel):
    citation_id: str
    document_id: str
    chunk_id: str
    title: str
    source: str
    source_url: str | None = None
    updated_at: str | None = None
    snippet: str
    source_type: str = "knowledge"
    tool_name: str | None = None
    observed_at: str | None = None


class RAGResult(BaseModel):
    grounded: bool
    confidence: float = Field(ge=0.0, le=1.0)
    context: str = ""
    citations: list[Citation] = Field(default_factory=list)
    hits: list[RetrievalHit] = Field(default_factory=list)
    gate_reason: str | None = None
