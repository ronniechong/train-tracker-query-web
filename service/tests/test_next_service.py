import httpx
import pytest

from src.pipeline.gate2 import ResolvedStations
from src.pipeline.next_service import UnknownStation, find_next_service
from src.pipeline.stations_cache import ScheduleUnavailable

_STATIONS = ResolvedStations(
    from_station_id="richmond-1",
    from_station_name="Richmond Railway Station",
    to_station_id="flinders-1",
    to_station_name="Flinders Street Railway Station",
)


_RealAsyncClient = httpx.AsyncClient


def _client_with_response(handler):
    def factory(*args, **kwargs):
        return _RealAsyncClient(transport=httpx.MockTransport(handler))

    return factory


async def test_sends_canonical_station_names_as_query_params(monkeypatch):
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["params"] = dict(request.url.params)
        return httpx.Response(
            200,
            json={
                "from_station": {"station_id": "richmond-1", "name": "Richmond Railway Station"},
                "to_station": {
                    "station_id": "flinders-1",
                    "name": "Flinders Street Railway Station",
                },
                "generated_at": "2026-08-26T08:00:00Z",
                "reason": None,
                "legs": [],
            },
        )

    monkeypatch.setattr(httpx, "AsyncClient", _client_with_response(handler))
    await find_next_service(_STATIONS)
    assert captured["params"] == {
        "from": "Richmond Railway Station",
        "to": "Flinders Street Railway Station",
    }


async def test_sends_after_param_when_time_given(monkeypatch):
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["params"] = dict(request.url.params)
        return httpx.Response(
            200,
            json={
                "from_station": {"station_id": "richmond-1", "name": "Richmond Railway Station"},
                "to_station": {"station_id": "flinders-1", "name": "Flinders Street Railway Station"},
                "generated_at": "2026-08-26T08:00:00Z",
                "reason": None,
                "legs": [],
            },
        )

    monkeypatch.setattr(httpx, "AsyncClient", _client_with_response(handler))
    await find_next_service(_STATIONS, requested_time="17:30")
    assert "after" in captured["params"]
    assert captured["params"]["after"].endswith("+00:00") or captured["params"]["after"].endswith("Z")


async def test_omits_after_param_when_no_time_given(monkeypatch):
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["params"] = dict(request.url.params)
        return httpx.Response(
            200,
            json={
                "from_station": {"station_id": "richmond-1", "name": "Richmond Railway Station"},
                "to_station": {"station_id": "flinders-1", "name": "Flinders Street Railway Station"},
                "generated_at": "2026-08-26T08:00:00Z",
                "reason": None,
                "legs": [],
            },
        )

    monkeypatch.setattr(httpx, "AsyncClient", _client_with_response(handler))
    await find_next_service(_STATIONS, requested_time=None)
    assert "after" not in captured["params"]


async def test_ignores_malformed_time():
    from src.pipeline.next_service import _after_param

    assert _after_param("not a time") is None
    assert _after_param(None) is None


async def test_converts_melbourne_local_time_to_utc():
    from datetime import datetime, timezone
    from zoneinfo import ZoneInfo

    from src.pipeline.next_service import _after_param

    result = _after_param("17:30")
    parsed = datetime.fromisoformat(result)
    local = parsed.astimezone(ZoneInfo("Australia/Melbourne"))
    assert local.hour == 17
    assert local.minute == 30
    assert parsed.astimezone(timezone.utc) == parsed


async def test_raises_unknown_station_on_404(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            404,
            json={"detail": {"reason": "unknown_station", "message": "not found"}},
        )

    monkeypatch.setattr(httpx, "AsyncClient", _client_with_response(handler))
    with pytest.raises(UnknownStation):
        await find_next_service(_STATIONS)


async def test_raises_schedule_unavailable_on_503(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"detail": "no snapshot pinned"})

    monkeypatch.setattr(httpx, "AsyncClient", _client_with_response(handler))
    with pytest.raises(ScheduleUnavailable):
        await find_next_service(_STATIONS)
