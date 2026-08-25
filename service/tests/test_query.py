from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from src.main import MAX_AUDIO_BYTES, app

client = TestClient(app)


def test_query_rejects_audio_over_5mb():
    oversized = b"0" * (MAX_AUDIO_BYTES + 1)
    response = client.post("/api/query", content=oversized)
    assert response.status_code == 413


def test_query_returns_not_implemented_for_unbuilt_gate2():
    with patch(
        "src.pipeline.orchestrator.stt.transcribe",
        new=AsyncMock(return_value="when's the next train from Richmond"),
    ):
        response = client.post("/api/query", content=b"short audio")
    assert response.status_code == 501
