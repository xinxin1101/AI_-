from pydantic import BaseModel, Field


class SourceSpec(BaseModel):
    source_id: str = Field(min_length=1, max_length=120)
    name: str
    publisher: str
    url: str
    category: str = "general"
    authority_level: str = "official_operator"
    freshness_class: str = "static"
    refresh_hours: int = Field(default=168, ge=1, le=8760)
    content_selector: str | None = None
    tags: list[str] = Field(default_factory=list)
    enabled: bool = True


class SourceSnapshot(BaseModel):
    source_id: str
    source_url: str
    fetched_at: str
    title: str
    text: str
    content_hash: str
    status_code: int = 200


class PipelineReport(BaseModel):
    source_count: int
    fetched_count: int
    document_count: int
    failures: dict[str, str] = Field(default_factory=dict)
