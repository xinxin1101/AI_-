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
    llm_force_stream: bool = False
    llm_modalities: str = "text"
    llm_extra_body_json: str = "{}"
    llm_capture_stream_usage: bool = False

    # P3 short-term conversation state.
    session_max_messages: int = Field(default=20, ge=2, le=200)
    session_backend: str = "memory"
    session_ttl_seconds: int = Field(default=86400, ge=60, le=2592000)
    redis_url: str = "redis://localhost:6379/0"
    redis_prefix: str = "guilin-ai"
    redis_socket_timeout_seconds: float = Field(default=3.0, gt=0, le=30)

    # P3 durable persistence. P3.5 prefers Alembic migrations over runtime DDL.
    persistence_enabled: bool = False
    database_url: str = "postgresql://guilin:guilin@localhost:5432/guilin_ai"
    database_min_pool_size: int = Field(default=1, ge=1, le=20)
    database_max_pool_size: int = Field(default=10, ge=1, le=50)
    database_command_timeout_seconds: float = Field(default=10.0, gt=0, le=120)
    database_auto_create: bool = False
    metrics_window_size: int = Field(default=1000, ge=50, le=100000)

    # P3.5 privacy and data retention.
    pii_redaction_enabled: bool = True
    trace_retention_days: int = Field(default=30, ge=1, le=3650)
    message_retention_days: int = Field(default=30, ge=1, le=3650)
    feedback_retention_days: int = Field(default=90, ge=1, le=3650)
    retention_cleanup_on_startup: bool = False

    # P3.5 API security and distributed rate limiting.
    api_auth_enabled: bool = False
    api_keys: str = ""
    rate_limit_enabled: bool = False
    rate_limit_backend: str = "redis"
    rate_limit_requests: int = Field(default=60, ge=1, le=100000)
    rate_limit_window_seconds: int = Field(default=60, ge=1, le=86400)
    rate_limit_redis_url: str = ""
    security_bypass_paths: str = "/,/health,/ready,/metrics,/docs,/redoc,/openapi.json"

    # P3.5 structured logging and OpenTelemetry.
    log_level: str = "INFO"
    log_json: bool = True
    otel_enabled: bool = False
    otel_service_name: str = "guilin-tourism-ai"
    otel_exporter_otlp_endpoint: str = "http://localhost:4318/v1/traces"
    otel_excluded_urls: str = "/health,/ready,/metrics"

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

    # P2/P2.5 agent and live-provider configuration.
    agent_enabled: bool = True
    tool_mock_mode: bool = True
    tool_timeout_seconds: float = Field(default=15.0, gt=0, le=120)
    tool_max_text_length: int = Field(default=120, ge=20, le=500)
    tool_retry_attempts: int = Field(default=2, ge=0, le=5)
    tool_retry_base_delay_seconds: float = Field(default=0.20, ge=0, le=10)
    tool_retry_max_delay_seconds: float = Field(default=2.0, ge=0, le=30)
    tool_circuit_failure_threshold: int = Field(default=3, ge=1, le=20)
    tool_circuit_recovery_seconds: float = Field(default=30.0, ge=1, le=600)
    tool_http_user_agent: str = "guilin-tourism-ai/0.3.5"

    weather_provider: str = "open_meteo"
    open_meteo_geocoding_url: str = "https://geocoding-api.open-meteo.com/v1/search"
    open_meteo_forecast_url: str = "https://api.open-meteo.com/v1/forecast"

    scenic_provider: str = "amap"
    route_provider: str = "amap"
    amap_api_key: str = ""
    amap_base_url: str = "https://restapi.amap.com"
    amap_region: str = "桂林"
    amap_citycode_default: str = "0773"

    agent_eval_dataset: str = "eval/intent_router_eval.jsonl"
    agent_eval_intent_accuracy_min: float = Field(default=0.90, ge=0, le=1)
    agent_eval_tool_selection_accuracy_min: float = Field(default=0.90, ge=0, le=1)

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

    @property
    def api_key_list(self) -> list[str]:
        return [item.strip() for item in self.api_keys.split(",") if item.strip()]

    @property
    def security_bypass_path_list(self) -> list[str]:
        return [item.strip() for item in self.security_bypass_paths.split(",") if item.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
