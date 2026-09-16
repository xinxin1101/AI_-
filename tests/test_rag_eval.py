import asyncio

from app.core.config import Settings
from app.eval.runner import run_rag_eval
from app.rag.service import RAGService
from app.services.llm import LLMClient


def _settings() -> Settings:
    return Settings(
        llm_mock_mode=True,
        rag_enabled=True,
        rag_knowledge_path="data/knowledge/verified",
        rag_eval_dataset="eval/rag_eval.jsonl",
        embedding_provider="hash",
        embedding_dimension=256,
        rag_vector_backend="memory",
        rerank_mode="local",
        rag_confidence_threshold=0.35,
        rag_eval_recall_at_5_min=0.75,
        rag_eval_mrr_min=0.65,
        rag_eval_grounding_accuracy_min=0.75,
        rag_eval_citation_hit_rate_min=0.75,
    )


def test_time_sensitive_query_requires_fresh_dynamic_evidence() -> None:
    service = RAGService(_settings())
    result = asyncio.run(service.retrieve("龙脊梯田当前是否24小时开放？"))
    assert result.grounded is False
    assert result.gate_reason in {"fresh_evidence_required", "low_confidence"}


def test_eval_suite_meets_p15_floor() -> None:
    report = asyncio.run(run_rag_eval(_settings()))
    assert report.passed, report.model_dump_json(indent=2)
    assert report.case_count >= 15
    assert report.recall_at_5 >= 0.75


def test_llm_adapter_keeps_model_replaceable_and_supports_omni_stream_mode() -> None:
    settings = Settings(
        llm_mock_mode=False,
        llm_model="qwen3.5-omni-flash",
        llm_force_stream=True,
        llm_modalities="text",
        llm_extra_body_json='{"enable_thinking": false}',
    )
    client = LLMClient(settings)
    payload = client._payload([], "你好", stream=True)
    assert payload["model"] == "qwen3.5-omni-flash"
    assert payload["stream"] is True
    assert payload["modalities"] == ["text"]
    assert payload["enable_thinking"] is False
