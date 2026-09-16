from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_grounded_chat_returns_citations() -> None:
    response = client.post("/api/v1/chat", json={"message": "象鼻山在哪里？"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["grounded"] is True
    assert payload["confidence"] >= 0.35
    assert payload["citations"]
    assert payload["citations"][0]["citation_id"].startswith("C")


def test_unknown_question_is_blocked_by_confidence_gate() -> None:
    response = client.post(
        "/api/v1/chat",
        json={"message": "火星基地量子电梯维护周期是多少？"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["grounded"] is False
    assert payload["citations"] == []
    assert "没有检索到足够可靠" in payload["answer"]


def test_stream_meta_contains_rag_grounding() -> None:
    with client.stream(
        "POST",
        "/api/v1/chat/stream",
        json={"message": "介绍一下龙脊梯田"},
    ) as response:
        body = "".join(response.iter_text())
    assert response.status_code == 200
    assert "event: meta" in body
    assert '"grounded": true' in body
    assert '"citations"' in body
    assert "event: token" in body
    assert "event: done" in body
