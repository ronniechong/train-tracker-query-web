from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from src.main import MAX_AUDIO_BYTES, app
from src.pipeline.gate2 import ExtractedQuery
from src.pipeline.stations_cache import Route, ScheduleUnavailable, Station

client = TestClient(app)

_RICHMOND = Station(
    station_id="richmond-1",
    name="Richmond Railway Station",
    routes=[Route(route_id="r1", short_name="Belgrave", long_name="Belgrave - City")],
)
_FLINDERS = Station(
    station_id="flinders-1",
    name="Flinders Street Railway Station",
    routes=[Route(route_id="r1", short_name="Belgrave", long_name="Belgrave - City")],
)


def test_query_rejects_audio_over_5mb():
    oversized = b"0" * (MAX_AUDIO_BYTES + 1)
    response = client.post("/api/query", content=oversized)
    assert response.status_code == 413


def test_query_returns_not_implemented_for_unbuilt_next_service():
    with (
        patch(
            "src.pipeline.orchestrator.stt.transcribe",
            new=AsyncMock(return_value="when's the next train from Richmond to Flinders Street"),
        ),
        patch(
            "src.pipeline.gate2.extract",
            new=AsyncMock(
                return_value=ExtractedQuery(
                    from_station="Richmond",
                    to_station="Flinders Street",
                    route_hint=None,
                    time=None,
                )
            ),
        ),
        patch(
            "src.pipeline.gate2.get_stations",
            new=AsyncMock(return_value=[_RICHMOND, _FLINDERS]),
        ),
    ):
        response = client.post("/api/query", content=b"short audio")
    assert response.status_code == 501


def test_query_returns_503_when_schedule_unavailable():
    with (
        patch(
            "src.pipeline.orchestrator.stt.transcribe",
            new=AsyncMock(return_value="when's the next train from Richmond to Flinders Street"),
        ),
        patch(
            "src.pipeline.gate2.extract",
            new=AsyncMock(
                return_value=ExtractedQuery(
                    from_station="Richmond",
                    to_station="Flinders Street",
                    route_hint=None,
                    time=None,
                )
            ),
        ),
        patch(
            "src.pipeline.gate2.get_stations",
            new=AsyncMock(side_effect=ScheduleUnavailable("no snapshot pinned")),
        ),
    ):
        response = client.post("/api/query", content=b"short audio")
    assert response.status_code == 503
