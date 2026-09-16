from __future__ import annotations

import json
import os
from pathlib import Path
from time import perf_counter

from fastapi.testclient import TestClient

from app.main import app


DATASET = Path("eval/rc1_e2e.jsonl")
RESULT_PATH = Path(os.getenv("RC1_RESULT_PATH", "rc1-results.json"))


def load_cases() -> list[dict]:
    return [
        json.loads(line)
        for line in DATASET.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def percentile(values: list[float], ratio: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int((len(ordered) - 1) * ratio + 0.999999)))
    return ordered[index]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    cases = load_cases()
    session_ids: dict[str, str] = {}
    results: list[dict] = []
    latencies: list[float] = []

    with TestClient(app) as client:
        ready = client.get("/ready")
        require(ready.status_code == 200, f"readiness failed: {ready.status_code} {ready.text}")

        for case in cases:
            request_payload: dict[str, str] = {"message": case["message"]}
            session_key = case.get("session")
            if session_key and session_key in session_ids:
                request_payload["session_id"] = session_ids[session_key]

            started = perf_counter()
            response = client.post("/api/v1/chat", json=request_payload)
            latency_ms = (perf_counter() - started) * 1000
            latencies.append(latency_ms)
            require(response.status_code == 200, f"{case['id']} HTTP {response.status_code}: {response.text}")
            payload = response.json()

            if session_key:
                session_ids.setdefault(session_key, payload["session_id"])
                require(
                    payload["session_id"] == session_ids[session_key],
                    f"{case['id']} changed session_id within the same conversation",
                )

            require(payload["intent"] == case["expected_intent"], f"{case['id']} intent={payload['intent']}")
            require(payload["grounded"] is case["expected_grounded"], f"{case['id']} grounded={payload['grounded']}")
            require(len(payload.get("citations") or []) >= case.get("min_citations", 0), f"{case['id']} citations too few")
            require(bool((payload.get("answer") or "").strip()), f"{case['id']} empty answer")

            if "expected_context_resolved" in case:
                require(
                    payload.get("context_resolved") is case["expected_context_resolved"],
                    f"{case['id']} context_resolved={payload.get('context_resolved')}",
                )
            if case.get("expected_standalone_contains"):
                require(
                    case["expected_standalone_contains"] in (payload.get("standalone_query") or ""),
                    f"{case['id']} standalone_query={payload.get('standalone_query')}",
                )
            expected_tool = case.get("expected_tool")
            tool_names = [item.get("tool_name") for item in payload.get("tool_calls") or []]
            if expected_tool:
                require(expected_tool in tool_names, f"{case['id']} tools={tool_names}")

            trace_response = client.get(f"/api/v1/observability/traces/{payload['trace_id']}")
            require(trace_response.status_code == 200, f"{case['id']} trace lookup failed")
            trace = trace_response.json()
            require(trace.get("trace_id") == payload["trace_id"], f"{case['id']} trace correlation mismatch")
            require(trace.get("session_id") == payload["session_id"], f"{case['id']} trace session mismatch")

            results.append(
                {
                    "id": case["id"],
                    "trace_id": payload["trace_id"],
                    "session_id": payload["session_id"],
                    "latency_ms": round(latency_ms, 3),
                    "intent": payload["intent"],
                    "grounded": payload["grounded"],
                    "gate_reason": payload.get("gate_reason"),
                    "standalone_query": payload.get("standalone_query"),
                    "context_resolved": payload.get("context_resolved"),
                    "context_resolution_reason": payload.get("context_resolution_reason"),
                    "tool_names": tool_names,
                    "tool_attempts": [item.get("attempts") for item in payload.get("tool_calls") or []],
                    "citation_count": len(payload.get("citations") or []),
                    "answer_chars": len(payload.get("answer") or ""),
                    "answer_has_citation_marker": "[C" in (payload.get("answer") or ""),
                    "prompt_tokens": trace.get("prompt_tokens"),
                    "completion_tokens": trace.get("completion_tokens"),
                    "total_tokens": trace.get("total_tokens"),
                    "trace_tool_calls": len(trace.get("tool_calls") or []),
                    "trace_citations": len(trace.get("citations") or []),
                }
            )

        metrics_response = client.get("/api/v1/observability/metrics/summary")
        require(metrics_response.status_code == 200, "metrics summary unavailable")
        metrics = metrics_response.json()

    known_tokens = [item["total_tokens"] for item in results if isinstance(item.get("total_tokens"), int)]
    summary = {
        "case_count": len(results),
        "success_count": len(results),
        "p50_latency_ms": round(percentile(latencies, 0.50), 3),
        "p95_latency_ms": round(percentile(latencies, 0.95), 3),
        "token_usage_known_cases": len(known_tokens),
        "total_tokens": sum(known_tokens),
        "grounded_cases": sum(1 for item in results if item["grounded"]),
        "fallback_cases": sum(1 for item in results if not item["grounded"]),
        "tool_cases": sum(1 for item in results if item["tool_names"]),
        "citation_marker_cases": sum(1 for item in results if item["answer_has_citation_marker"]),
        "metrics_snapshot": metrics,
        "cases": results,
    }
    RESULT_PATH.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
