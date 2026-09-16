from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.agent.context import context_resolver
from app.agent.router import classify_intent, tool_for_intent


DEFAULT_DATASET = Path("eval/multiturn_eval.jsonl")


def load_cases(path: Path) -> list[dict]:
    cases: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            cases.append(json.loads(line))
    return cases


def evaluate(path: Path) -> dict:
    cases = load_cases(path)
    failures: list[dict] = []
    query_hits = 0
    resolved_hits = 0
    intent_hits = 0
    tool_hits = 0
    contextual_total = 0
    contextual_query_hits = 0

    for case in cases:
        resolution = context_resolver.resolve(case["history"], case["query"])
        intent = classify_intent(resolution.standalone_query)
        tool = tool_for_intent(intent)

        query_ok = resolution.standalone_query == case["expected_query"]
        resolved_ok = resolution.resolved is bool(case["expected_resolved"])
        intent_ok = intent.value == case["expected_intent"]
        tool_ok = tool == case.get("expected_tool")

        query_hits += int(query_ok)
        resolved_hits += int(resolved_ok)
        intent_hits += int(intent_ok)
        tool_hits += int(tool_ok)
        if case["expected_resolved"]:
            contextual_total += 1
            contextual_query_hits += int(query_ok)

        if not all((query_ok, resolved_ok, intent_ok, tool_ok)):
            failures.append(
                {
                    "id": case["id"],
                    "query": case["query"],
                    "actual_query": resolution.standalone_query,
                    "expected_query": case["expected_query"],
                    "actual_resolved": resolution.resolved,
                    "expected_resolved": case["expected_resolved"],
                    "actual_intent": intent.value,
                    "expected_intent": case["expected_intent"],
                    "actual_tool": tool,
                    "expected_tool": case.get("expected_tool"),
                    "reason": resolution.reason,
                }
            )

    total = len(cases)
    denominator = max(total, 1)
    return {
        "cases": total,
        "contextual_cases": contextual_total,
        "standalone_query_accuracy": query_hits / denominator,
        "resolved_flag_accuracy": resolved_hits / denominator,
        "contextual_query_accuracy": contextual_query_hits / max(contextual_total, 1),
        "intent_accuracy": intent_hits / denominator,
        "tool_selection_accuracy": tool_hits / denominator,
        "failures": failures,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate deterministic multi-turn context resolution")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--fail-on-threshold", action="store_true")
    parser.add_argument("--min-query-accuracy", type=float, default=1.0)
    parser.add_argument("--min-resolved-accuracy", type=float, default=1.0)
    parser.add_argument("--min-intent-accuracy", type=float, default=1.0)
    parser.add_argument("--min-tool-accuracy", type=float, default=1.0)
    args = parser.parse_args()

    result = evaluate(args.dataset)
    passed = (
        result["standalone_query_accuracy"] >= args.min_query_accuracy
        and result["contextual_query_accuracy"] >= args.min_query_accuracy
        and result["resolved_flag_accuracy"] >= args.min_resolved_accuracy
        and result["intent_accuracy"] >= args.min_intent_accuracy
        and result["tool_selection_accuracy"] >= args.min_tool_accuracy
    )
    result["thresholds"] = {
        "standalone_query_accuracy": args.min_query_accuracy,
        "resolved_flag_accuracy": args.min_resolved_accuracy,
        "intent_accuracy": args.min_intent_accuracy,
        "tool_selection_accuracy": args.min_tool_accuracy,
    }
    result["passed"] = passed
    print(json.dumps(result, ensure_ascii=False, indent=2))

    if args.fail_on_threshold and not passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
