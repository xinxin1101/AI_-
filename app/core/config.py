from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Guilin Tourism AI Assistant"
    app_env: str = "development"
    api_prefix: str = "/api/v1"
    cors_origins: str = "*"

    llm_mock_mode: bool = True
    llm_base_url: str = "https://api.openai.com/v1"
    llm_api_key: str = ""
    llm_model: str = "gpt-4o-mini"
    llm_timeout_seconds: float = Field(default=60.0, gt=0)
    llm_temperature: float = Field(default=0.3, ge=0, le=2)
    llm_max_tokens: int = Field(default=800, gt=0)
    # Some multimodal providers (for example Qwen3.5-Omni) require streaming.
    # When enabled, the non-stream /chat API aggregates provider stream chunks.
    llm_force_stream: bool = False
    llm_modalities: str = "text"
    llm_extra_body_json: str = "{}"

    session_max_messages: int = Field(default=20, ge=2, le=200)

    rag_enabled: bool = True
    rag_knowledge_path: str = "data/knowledge/verified"
    rag_chunk_size_chars: int = Field(default=700, ge=100, le=4000)
    rag_chunk_overlap_chars: int = Field(default=100, ge=0, le=1000)
    rag_dense_top_k: int = Field(default=8, ge=1, le=50)
    rag_bm25_top_k: int = Field(default=8, ge=1, le=50)
    rag_fused_top_k: int = Field(default=10, ge=1, le=50)
    rag_rerank_top_k: int = Field(default=5, ge=1, le=20)
    rag_confidence_threshold: float = Field(default=0.35, ge=0, le=1)
    rag_max_context_chars: int = Field(default=6000, ge=500, le=30000)
    rag_citation_snippet_chars: int = Field(default=180, ge=50, le=1000)

    embedding_provider: str = "hash"
    embedding_base_url: str = "https://api.openai.com/v1"
    embedding_api_key: str = ""
    embedding_model: str = "text-embedding-3-small"
    embedding_dimension: int = Field(default=256, ge=32, le=8192)
    embedding_timeout_seconds: float = Field(default=60.0, gt=0)

    rag_vector_backend: str = "memory"
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str = ""
    qdrant_collection: str = "guilin_tourism"
    qdrant_timeout_seconds: float = Field(default=30.0, gt=0)

    rerank_mode: str = "local"
    rerank_base_url: str = ""
    rerank_api_key: str = ""
    rerank_model: str = "bge-reranker"
    rerank_timeout_seconds: float = Field(default=30.0, gt=0)

    knowledge_source_registry: str = "data/sources/guilin_official_sources.json"
    knowledge_snapshot_dir: str = "data/snapshots"
    knowledge_http_timeout_seconds: float = Field(default=30.0, gt=0)

    rag_eval_dataset: str = "eval/rag_eval.jsonl"
    rag_eval_recall_at_5_min: float = Field(default=0.80, ge=0, le=1)
    rag_eval_mrr_min: float = Field(default=0.70, ge=0, le=1)
    rag_eval_grounding_accuracy_min: float = Field(default=0.80, ge=0, le=1)
    rag_eval_citation_hit_rate_min: float = Field(default=0.80, ge=0, le=1)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def cors_origin_list(self) -> list[str]:
        if self.cors_origins.strip() == "*":
            return ["*"]
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]

    @property
    def llm_modalities_list(self) -> list[str]:
        return [item.strip() for item in self.llm_modalities.split(",") if item.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
