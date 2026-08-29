from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from src.main import MAX_AUDIO_BYTES, app
from src.pipeline.errors import UpstreamUnavailable
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


def test_query_returns_composed_answer_and_audio_on_success():
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
        patch(
            "src.pipeline.orchestrator.compose.compose_answer",
            new=AsyncMock(return_value="Next train departs shortly."),
        ),
        patch(
            "src.pipeline.orchestrator.tts.synthesize",
            new=AsyncMock(return_value="base64audio"),
        ),
    ):
        response = client.post("/api/query", content=b"short audio")
    assert response.status_code == 200
    body = response.json()
    assert body["text"] == "Next train departs shortly."
    assert body["audio"] == "base64audio"
    assert body["fallback_reason"] is None


def test_query_returns_highlights_built_from_real_leg_data():
    from src.main import limiter
    from src.pipeline.next_service import Leg

    limiter.reset()
    success_result = NextServiceResult(
        from_station=_FROM_REF,
        to_station=_TO_REF,
        generated_at="2026-08-26T08:00:00Z",
        reason=None,
        legs=[
            Leg(
                trip_id="t1",
                route_id="r1",
                headsign="Test",
                from_station=_FROM_REF,
                from_platform_code="3",
                departure_time="2026-08-26T03:08:00Z",
                to_station=_TO_REF,
                arrival_time="2026-08-26T03:21:00Z",
            )
        ],
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
        patch(
            "src.pipeline.orchestrator.compose.compose_answer",
            new=AsyncMock(return_value="Next train departs shortly."),
        ),
        patch(
            "src.pipeline.orchestrator.tts.synthesize",
            new=AsyncMock(return_value=None),
        ),
    ):
        response = client.post("/api/query", content=b"short audio")
    limiter.reset()
    assert response.status_code == 200
    highlights = response.json()["highlights"]
    kinds_and_texts = {(h["kind"], h["text"]) for h in highlights}
    assert ("station", "Richmond Railway Station".replace(" Railway", "")) in kinds_and_texts
    assert ("platform", "Platform 3") in kinds_and_texts


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


def test_query_clarification_includes_structured_suggestion(monkeypatch):
    from src.pipeline.gate2 import ClarificationNeeded
    from src.pipeline.models import FallbackReason

    async def fake_transcribe(audio_bytes, **_kwargs):
        return "when's the next train from Murubak to Richmond"

    async def fake_extract(transcript, **_kwargs):
        return ExtractedQuery(from_station="Murubak", to_station="Richmond", route_hint=None, time=None)

    async def fake_resolve_stations(extracted, **_kwargs):
        raise ClarificationNeeded(
            "I heard 'Murubak' — did you mean Mooroolbark Railway Station?",
            FallbackReason.LOW_CONFIDENCE_STATION,
            "from",
            suggested_station_name="Mooroolbark Railway Station",
        )

    with (
        patch("src.pipeline.orchestrator.stt.transcribe", new=AsyncMock(side_effect=fake_transcribe)),
        patch("src.pipeline.gate2.extract", new=AsyncMock(side_effect=fake_extract)),
        patch("src.pipeline.gate2.resolve_stations", new=AsyncMock(side_effect=fake_resolve_stations)),
    ):
        response = client.post("/api/query", content=b"short audio")

    assert response.status_code == 200
    body = response.json()
    assert body["clarification"]["field"] == "from"
    assert body["clarification"]["suggested_station_name"] == "Mooroolbark Railway Station"
    assert body["clarification"]["extracted"]["from_station"] == "Murubak"
    assert body["clarification"]["extracted"]["to_station"] == "Richmond"


def test_query_text_runs_full_pipeline():
    p1, p2, p3 = _patched_up_to_gate2()
    success_result = NextServiceResult(
        from_station=_FROM_REF,
        to_station=_TO_REF,
        generated_at="2026-08-26T08:00:00Z",
        reason=None,
        legs=[],
    )
    with (
        p1,
        p2,
        p3,
        patch(
            "src.pipeline.orchestrator.next_service.find_next_service",
            new=AsyncMock(return_value=success_result),
        ),
        patch(
            "src.pipeline.orchestrator.compose.compose_answer",
            new=AsyncMock(return_value="Next train departs shortly."),
        ),
        patch(
            "src.pipeline.orchestrator.tts.synthesize",
            new=AsyncMock(return_value="base64audio"),
        ),
    ):
        response = client.post("/api/query/text", json={"text": "when's the next train from Richmond to Flinders Street"})
    assert response.status_code == 200
    assert response.json()["text"] == "Next train departs shortly."


def test_query_text_rejects_overlong_text():
    from src.main import MAX_TEXT_LENGTH

    response = client.post("/api/query/text", json={"text": "x" * (MAX_TEXT_LENGTH + 1)})
    assert response.status_code == 413


def test_query_confirm_skips_stt_and_extraction():
    success_result = NextServiceResult(
        from_station=_FROM_REF,
        to_station=_TO_REF,
        generated_at="2026-08-26T08:00:00Z",
        reason=None,
        legs=[],
    )
    with (
        patch(
            "src.pipeline.gate2.get_stations",
            new=AsyncMock(return_value=[_RICHMOND, _FLINDERS]),
        ),
        patch(
            "src.pipeline.orchestrator.next_service.find_next_service",
            new=AsyncMock(return_value=success_result),
        ),
        patch(
            "src.pipeline.orchestrator.compose.compose_answer",
            new=AsyncMock(return_value="Next train departs shortly."),
        ),
        patch(
            "src.pipeline.orchestrator.tts.synthesize",
            new=AsyncMock(return_value="base64audio"),
        ),
    ):
        response = client.post(
            "/api/query/confirm",
            json={
                "from_station": "Richmond",
                "to_station": "Flinders Street",
                "route_hint": None,
                "time": None,
            },
        )
    assert response.status_code == 200
    assert response.json()["text"] == "Next train departs shortly."


def test_query_returns_service_unavailable_when_stt_fails():
    with patch(
        "src.pipeline.orchestrator.stt.transcribe",
        new=AsyncMock(side_effect=UpstreamUnavailable("STT request failed")),
    ):
        response = client.post("/api/query", content=b"short audio")
    assert response.status_code == 200
    body = response.json()
    assert body["fallback_reason"] == "service_unavailable"


def test_query_returns_service_unavailable_when_over_daily_cap():
    with patch("src.pipeline.orchestrator.tracing.is_over_daily_cap", return_value=True):
        response = client.post("/api/query", content=b"short audio")
    assert response.status_code == 200
    assert response.json()["fallback_reason"] == "service_unavailable"


def test_query_degrades_to_text_only_when_tts_fails():
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
        patch(
            "src.pipeline.orchestrator.compose.compose_answer",
            new=AsyncMock(return_value="Next train departs shortly."),
        ),
        patch(
            "src.pipeline.orchestrator.tts.synthesize",
            new=AsyncMock(side_effect=UpstreamUnavailable("TTS request failed")),
        ),
    ):
        response = client.post("/api/query", content=b"short audio")
    assert response.status_code == 200
    body = response.json()
    assert body["text"] == "Next train departs shortly."
    assert body["audio"] is None
    assert body["fallback_reason"] is None


def test_query_text_is_rate_limited_after_ten_per_minute():
    from src.main import limiter
    from src.pipeline.gate1 import Gate1Outcome

    limiter.reset()
    try:
        with patch(
            "src.pipeline.orchestrator.gate1.check",
            new=AsyncMock(return_value=Gate1Outcome.OFF_TOPIC),
        ):
            for _ in range(10):
                response = client.post("/api/query/text", json={"text": "x"})
                assert response.status_code != 429
            response = client.post("/api/query/text", json={"text": "x"})
        assert response.status_code == 429
    finally:
        limiter.reset()


def test_query_text_rate_limit_keys_on_x_real_ip_not_socket_peer():
    from src.main import limiter
    from src.pipeline.gate1 import Gate1Outcome

    limiter.reset()
    try:
        with patch(
            "src.pipeline.orchestrator.gate1.check",
            new=AsyncMock(return_value=Gate1Outcome.OFF_TOPIC),
        ):
            for _ in range(10):
                response = client.post(
                    "/api/query/text",
                    json={"text": "x"},
                    headers={"X-Real-IP": "203.0.113.1"},
                )
                assert response.status_code != 429
            exhausted = client.post(
                "/api/query/text",
                json={"text": "x"},
                headers={"X-Real-IP": "203.0.113.1"},
            )
            assert exhausted.status_code == 429

            # A different X-Real-IP gets its own bucket even though the
            # TestClient's raw socket peer is identical for both requests —
            # this is the whole point of trusting Caddy's header over
            # get_remote_address's raw-peer default.
            other_ip = client.post(
                "/api/query/text",
                json={"text": "x"},
                headers={"X-Real-IP": "203.0.113.2"},
            )
            assert other_ip.status_code != 429
    finally:
        limiter.reset()
