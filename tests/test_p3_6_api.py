from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_same_session_resolves_followup_before_routing() -> None:
    first = client.post(
        "/api/v1/chat",
        json={"message": "介绍一下象鼻山"},
    )
    assert first.status_code == 200
    session_id = first.json()["session_id"]

    second = client.post(
        "/api/v1/chat",
        json={
            "session_id": session_id,
            "message": "那它今天几点关门？",
        },
    )
    assert second.status_code == 200
    payload = second.json()
    assert payload["session_id"] == session_id
    assert payload["context_resolved"] is True
    assert payload["standalone_query"] == "象鼻山今天几点关门？"
    assert payload["context_resolution_reason"] == "pronoun_reference"
    assert payload["intent"] == "scenic_info"
    assert payload["tool_calls"][0]["tool_name"] == "scenic_info"


def test_stream_meta_exposes_context_resolution() -> None:
    first = client.post(
        "/api/v1/chat",
        json={"message": "今天桂林天气怎么样？"},
    ).json()

    with client.stream(
        "POST",
        "/api/v1/chat/stream",
        json={"session_id": first["session_id"], "message": "明天呢？"},
    ) as response:
        body = "".join(response.iter_text())

    assert response.status_code == 200
    assert '"context_resolved": true' in body
    assert '"standalone_query": "明天桂林天气怎么样？"' in body
    assert '"context_resolution_reason": "temporal_followup"' in body
    assert '"intent": "realtime_weather"' in body
