import json
from pathlib import Path

from app.core.config import Settings, get_settings
from app.eval.metrics import keyword_coverage, recall_at_k, reciprocal_rank
from app.eval.models import RAGEvalCase, RAGEvalCaseResult, RAGEvalReport
from app.rag.service import RAGService


def load_eval_cases(path_value: str) -> list[RAGEvalCase]:
    path = Path(path_value)
    cases: list[RAGEvalCase] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, raw in enumerate(handle, start=1):
            if not raw.strip():
                continue
            try:
                cases.append(RAGEvalCase.model_validate(json.loads(raw)))
            except (json.JSONDecodeError, ValueError) as exc:
                raise ValueError(f"Invalid eval case at {path}:{line_number}") from exc
    return cases


async def run_rag_eval(settings: Settings | None = None) -> RAGEvalReport:
    settings = settings or get_settings()
    service = RAGService(settings)
    cases = load_eval_cases(settings.rag_eval_dataset)
    results: list[RAGEvalCaseResult] = []

    for case in cases:
        result = await service.retrieve(case.query)
        retrieved_ids = [hit.chunk.document_id for hit in result.hits]
        expected = set(case.expected_document_ids)
        rr = reciprocal_rank(retrieved_ids, expected) if case.should_ground else 0.0
        recall5 = recall_at_k(retrieved_ids, expected, 5) if case.should_ground else 0.0
        citation_ids = {citation.document_id for citation in result.citations}
        citation_hit = (
            1.0 if case.should_ground and expected and bool(citation_ids & expected) else 0.0
        )
        evidence = keyword_coverage(result.context, case.expected_terms) if case.should_ground else 1.0
        results.append(
            RAGEvalCaseResult(
                case_id=case.case_id,
                should_ground=case.should_ground,
                grounded=result.grounded,
                expected_document_ids=case.expected_document_ids,
                retrieved_document_ids=retrieved_ids,
                reciprocal_rank=rr,
                recall_at_5=recall5,
                citation_hit=citation_hit,
                evidence_coverage=evidence,
                gate_reason=result.gate_reason,
            )
        )

    positives = [item for item in results if item.should_ground]
    recall5 = sum(item.recall_at_5 for item in positives) / max(len(positives), 1)
    mrr = sum(item.reciprocal_rank for item in positives) / max(len(positives), 1)
    grounding_accuracy = sum(item.grounded == item.should_ground for item in results) / max(len(results), 1)
    citation_hit_rate = sum(item.citation_hit for item in positives) / max(len(positives), 1)
    evidence_coverage = sum(item.evidence_coverage for item in positives) / max(len(positives), 1)
    thresholds = {
        "recall_at_5": settings.rag_eval_recall_at_5_min,
        "mrr": settings.rag_eval_mrr_min,
        "grounding_accuracy": settings.rag_eval_grounding_accuracy_min,
        "citation_hit_rate": settings.rag_eval_citation_hit_rate_min,
    }
    passed = (
        recall5 >= thresholds["recall_at_5"]
        and mrr >= thresholds["mrr"]
        and grounding_accuracy >= thresholds["grounding_accuracy"]
        and citation_hit_rate >= thresholds["citation_hit_rate"]
    )
    return RAGEvalReport(
        case_count=len(results),
        positive_case_count=len(positives),
        recall_at_5=round(recall5, 4),
        mrr=round(mrr, 4),
        grounding_accuracy=round(grounding_accuracy, 4),
        citation_hit_rate=round(citation_hit_rate, 4),
        evidence_coverage=round(evidence_coverage, 4),
        passed=passed,
        thresholds=thresholds,
        cases=results,
    )
