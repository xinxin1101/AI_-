from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_weather_query_uses_tool_instead_of_freshness_fallback() -> None:
    response = client.post("/api/v1/chat", json={"message": "明天去漓江会下雨吗？"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["intent"] == "realtime_weather"
    assert payload["grounded"] is True
    assert payload["gate_reason"] == "tool_evidence"
    tool_call = payload["tool_calls"][0]
    assert tool_call["tool_name"] == "weather"
    assert tool_call["status"] == "success"
    assert tool_call["attempts"] == 1
    assert tool_call["latency_ms"] == 0.0
    assert tool_call["circuit_state"] == "closed"
    assert any(
        item["source_type"] == "tool" and item["tool_name"] == "weather"
        for item in payload["citations"]
    )


def test_scenic_route_and_itinerary_branches() -> None:
    scenic = client.post(
        "/api/v1/chat",
        json={"message": "象鼻山今天几点关门？"},
    ).json()
    assert scenic["intent"] == "scenic_info"
    assert scenic["tool_calls"][0]["status"] == "success"

    route = client.post(
        "/api/v1/chat",
        json={"message": "从桂林北站到阳朔西街怎么走？"},
    ).json()
    assert route["intent"] == "route"
    assert route["tool_calls"][0]["tool_name"] == "route"
    assert route["grounded"] is True

    itinerary = client.post(
        "/api/v1/chat",
        json={"message": "桂林两天怎么玩，帮我安排行程"},
    ).json()
    assert itinerary["intent"] == "itinerary"
    assert itinerary["tool_calls"][0]["tool_name"] == "itinerary_planner"


def test_ood_question_still_falls_back_without_tool_hallucination() -> None:
    payload = client.post(
        "/api/v1/chat",
        json={"message": "火星基地量子电梯维护周期是多少？"},
    ).json()
    assert payload["intent"] == "knowledge"
    assert payload["grounded"] is False
    assert payload["tool_calls"] == []
    assert "没有检索到足够可靠" in payload["answer"]


def test_stream_meta_exposes_agent_decision_and_tool_trace() -> None:
    with client.stream(
        "POST",
        "/api/v1/chat/stream",
        json={"message": "明天桂林天气怎么样？"},
    ) as response:
        body = "".join(response.iter_text())
    assert response.status_code == 200
    assert '"intent": "realtime_weather"' in body
    assert '"tool_name": "weather"' in body
    assert '"attempts": 1' in body
    assert '"circuit_state": "closed"' in body
    assert '"gate_reason": "tool_evidence"' in body
    assert "event: token" in body
    assert "event: done" in body
