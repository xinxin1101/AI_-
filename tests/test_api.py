from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_health() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_session_chat_and_feedback_flow() -> None:
    session_response = client.post("/api/v1/session")
    assert session_response.status_code == 201
    session_id = session_response.json()["session_id"]

    chat_response = client.post(
        "/api/v1/chat",
        json={"session_id": session_id, "message": "桂林两天怎么玩？"},
    )
    assert chat_response.status_code == 200
    payload = chat_response.json()
    assert payload["session_id"] == session_id
    assert payload["trace_id"].startswith("tr_")
    assert payload["answer"]

    feedback_response = client.post(
        "/api/v1/feedback",
        json={
            "session_id": session_id,
            "trace_id": payload["trace_id"],
            "rating": "up",
            "comment": "P0 smoke test",
        },
    )
    assert feedback_response.status_code == 200
    assert feedback_response.json() == {"accepted": True}


def test_chat_can_create_session_implicitly() -> None:
    response = client.post(
        "/api/v1/chat",
        json={"message": "你好"},
    )
    assert response.status_code == 200
    assert response.json()["session_id"].startswith("sess_")


def test_streaming_chat_emits_expected_events() -> None:
    with client.stream(
        "POST",
        "/api/v1/chat/stream",
        json={"message": "介绍桂林"},
    ) as response:
        body = "".join(response.iter_text())

    assert response.status_code == 200
    assert "event: meta" in body
    assert "event: token" in body
    assert "event: done" in body


def test_feedback_rejects_unknown_session() -> None:
    response = client.post(
        "/api/v1/feedback",
        json={"session_id": "sess_missing", "rating": "down"},
    )
    assert response.status_code == 404
