import argparse

from app.core.config import Settings
from app.eval.agent_router import (
    evaluate_router,
    load_router_eval_cases,
    metrics_as_json,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate deterministic intent/tool routing.")
    parser.add_argument("--fail-on-threshold", action="store_true")
    args = parser.parse_args()

    settings = Settings()
    cases = load_router_eval_cases(settings.agent_eval_dataset)
    metrics = evaluate_router(cases)
    print(metrics_as_json(metrics))

    if args.fail_on_threshold:
        if metrics.intent_accuracy < settings.agent_eval_intent_accuracy_min:
            return 1
        if (
            metrics.tool_selection_accuracy
            < settings.agent_eval_tool_selection_accuracy_min
        ):
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
