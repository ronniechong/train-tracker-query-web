from fastapi.testclient import TestClient

from src.main import app
from src.pipeline import tracing

client = TestClient(app)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_feedback_endpoint_calls_record_feedback(monkeypatch):
    calls = []
    monkeypatch.setattr(tracing, "record_feedback", lambda trace_id, thumbs_up: calls.append((trace_id, thumbs_up)))

    response = client.post("/api/feedback", json={"trace_id": "abc-123", "thumbs_up": True})

    assert response.status_code == 200
    assert calls == [("abc-123", True)]
