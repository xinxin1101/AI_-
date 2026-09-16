from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_chat_populates_operational_metrics() -> None:
    response = client.post("/api/v1/chat", json={"message": "明天桂林天气怎么样？"})
    assert response.status_code == 200
    summary = client.get("/api/v1/observability/metrics/summary")
    assert summary.status_code == 200
    payload = summary.json()
    assert payload["window_size"] >= 1
    assert payload["latency_ms"]["p50"] >= 0
    assert payload["intent_distribution"].get("realtime_weather", 0) >= 1
    assert payload["tool_success_rate"] is not None


def test_prometheus_and_readiness_endpoints() -> None:
    metrics = client.get("/metrics")
    assert metrics.status_code == 200
    assert "guilin_ai_latency_p95_ms" in metrics.text
    ready = client.get("/ready")
    assert ready.status_code == 200
    assert ready.json()["status"] == "ready"


def test_trace_lookup_reports_disabled_persistence_by_default() -> None:
    response = client.get("/api/v1/observability/traces/tr_missing")
    assert response.status_code == 503
