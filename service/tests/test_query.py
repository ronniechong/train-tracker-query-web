from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from src.main import MAX_AUDIO_BYTES, app
from src.pipeline.gate2 import ExtractedQuery
from src.pipeline.next_service import NextServiceResult, StationRef, UnknownStation
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
_FROM_REF = StationRef(station_id="richmond-1", name="Richmond Railway Station")
_TO_REF = StationRef(station_id="flinders-1", name="Flinders Street Railway Station")


def _patched_up_to_gate2():
    return (
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
    )


def test_query_rejects_audio_over_5mb():
    oversized = b"0" * (MAX_AUDIO_BYTES + 1)
    response = client.post("/api/query", content=oversized)
    assert response.status_code == 413


def test_query_returns_not_implemented_for_unbuilt_compose():
    success_result = NextServiceResult(
        from_station=_FROM_REF,
        to_station=_TO_REF,
        generated_at="2026-08-26T08:00:00Z",
        reason=None,
        legs=[],
    )
    p1, p2, p3 = _patched_up_to_gate2()
    with (
        p1,
        p2,
        p3,
        patch(
            "src.pipeline.orchestrator.next_service.find_next_service",
            new=AsyncMock(return_value=success_result),
        ),
    ):
        response = client.post("/api/query", content=b"short audio")
    assert response.status_code == 501


def test_query_returns_fallback_for_no_service_today():
    reason_result = NextServiceResult(
        from_station=_FROM_REF,
        to_station=_TO_REF,
        generated_at="2026-08-26T08:00:00Z",
        reason="no_service_today",
        legs=[],
    )
    p1, p2, p3 = _patched_up_to_gate2()
    with (
        p1,
        p2,
        p3,
        patch(
            "src.pipeline.orchestrator.next_service.find_next_service",
            new=AsyncMock(return_value=reason_result),
        ),
    ):
        response = client.post("/api/query", content=b"short audio")
    assert response.status_code == 200
    assert response.json()["fallback_reason"] == "no_service_today"


def test_query_returns_fallback_for_no_route_found():
    reason_result = NextServiceResult(
        from_station=_FROM_REF,
        to_station=_TO_REF,
        generated_at="2026-08-26T08:00:00Z",
        reason="no_route_found",
        legs=[],
    )
    p1, p2, p3 = _patched_up_to_gate2()
    with (
        p1,
        p2,
        p3,
        patch(
            "src.pipeline.orchestrator.next_service.find_next_service",
            new=AsyncMock(return_value=reason_result),
        ),
    ):
        response = client.post("/api/query", content=b"short audio")
    assert response.status_code == 200
    body = response.json()
    assert body["fallback_reason"] == "no_route_found"
    assert "ptv.vic.gov.au" in body["text"]


def test_query_returns_fallback_for_unknown_station():
    p1, p2, p3 = _patched_up_to_gate2()
    with (
        p1,
        p2,
        p3,
        patch(
            "src.pipeline.orchestrator.next_service.find_next_service",
            new=AsyncMock(side_effect=UnknownStation("unknown station")),
        ),
    ):
        response = client.post("/api/query", content=b"short audio")
    assert response.status_code == 200
    assert response.json()["fallback_reason"] == "unknown_station"


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
