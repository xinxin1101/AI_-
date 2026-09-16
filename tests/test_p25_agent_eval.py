from app.core.config import Settings
from app.eval.agent_router import evaluate_router, load_router_eval_cases


def test_curated_router_eval_meets_p25_floor() -> None:
    settings = Settings()
    metrics = evaluate_router(load_router_eval_cases(settings.agent_eval_dataset))

    assert metrics.case_count >= 30
    assert metrics.intent_accuracy >= settings.agent_eval_intent_accuracy_min
    assert (
        metrics.tool_selection_accuracy
        >= settings.agent_eval_tool_selection_accuracy_min
    )
