import json
from pathlib import Path

from pydantic import BaseModel, Field

from app.agent.models import Intent
from app.agent.router import classify_intent, tool_for_intent


class RouterEvalCase(BaseModel):
    case_id: str
    query: str
    expected_intent: Intent
    expected_tool: str | None = None
    gate_reason: str | None = None


class RouterEvalMetrics(BaseModel):
    case_count: int
    intent_accuracy: float = Field(ge=0, le=1)
    tool_selection_accuracy: float = Field(ge=0, le=1)
    failures: list[dict] = Field(default_factory=list)


def load_router_eval_cases(path: str | Path) -> list[RouterEvalCase]:
    cases: list[RouterEvalCase] = []
    with Path(path).open("r", encoding="utf-8") as handle:
        for line_number, raw in enumerate(handle, start=1):
            line = raw.strip()
            if not line:
                continue
            try:
                cases.append(RouterEvalCase.model_validate_json(line))
            except Exception as exc:
                raise ValueError(f"invalid router eval case at line {line_number}") from exc
    return cases


def evaluate_router(cases: list[RouterEvalCase]) -> RouterEvalMetrics:
    if not cases:
        return RouterEvalMetrics(
            case_count=0,
            intent_accuracy=0.0,
            tool_selection_accuracy=0.0,
        )

    intent_hits = 0
    tool_hits = 0
    failures: list[dict] = []

    for case in cases:
        predicted_intent = classify_intent(case.query, case.gate_reason)
        predicted_tool = tool_for_intent(predicted_intent)
        intent_ok = predicted_intent == case.expected_intent
        tool_ok = predicted_tool == case.expected_tool
        intent_hits += int(intent_ok)
        tool_hits += int(tool_ok)
        if not intent_ok or not tool_ok:
            failures.append(
                {
                    "case_id": case.case_id,
                    "query": case.query,
                    "expected_intent": case.expected_intent.value,
                    "predicted_intent": predicted_intent.value,
                    "expected_tool": case.expected_tool,
                    "predicted_tool": predicted_tool,
                }
            )

    count = len(cases)
    return RouterEvalMetrics(
        case_count=count,
        intent_accuracy=intent_hits / count,
        tool_selection_accuracy=tool_hits / count,
        failures=failures,
    )


def metrics_as_json(metrics: RouterEvalMetrics) -> str:
    return json.dumps(metrics.model_dump(), ensure_ascii=False, indent=2)
