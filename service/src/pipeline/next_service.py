import os
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import httpx
from pydantic import BaseModel

from .gate2 import ResolvedStations
from .stations_cache import ScheduleUnavailable

_MELBOURNE_TZ = ZoneInfo("Australia/Melbourne")


class StationRef(BaseModel):
    station_id: str
    name: str


class Leg(BaseModel):
    trip_id: str
    route_id: str
    headsign: str
    from_station: StationRef
    from_platform_code: str | None = None
    departure_time: str
    to_station: StationRef
    to_platform_code: str | None = None
    arrival_time: str


class NextServiceResult(BaseModel):
    from_station: StationRef
    to_station: StationRef
    generated_at: str
    reason: str | None
    legs: list[Leg]


class UnknownStation(Exception):
    pass


def _base_url() -> str:
    return os.environ["TRAIN_TRACKER_API_BASE_URL"].rstrip("/")


def _client() -> httpx.AsyncClient:
    # trust_env=False: this call must never pick up HTTP_PROXY/HTTPS_PROXY
    # (the Groq/Langfuse egress-proxy, which can't route to train-tracker's
    # tailnet-only API at all). TRAIN_TRACKER_PROXY_URL, when set, is the
    # tailscale sidecar's own proxy instead — see deploy/docker-compose.yml.
    return httpx.AsyncClient(proxy=os.environ.get("TRAIN_TRACKER_PROXY_URL") or None, trust_env=False)


def _after_param(requested_time: str | None) -> str | None:
    """Converts a Gate 2-normalized "HH:MM" (assumed today, Melbourne
    local — see gate2's extraction prompt) into the UTC instant
    train-tracker's `after` param expects. Malformed input is ignored
    (falls back to "now") rather than failing the whole query over a
    time the user may not even have cared about getting exactly right."""
    if requested_time is None:
        return None
    try:
        hour, minute = (int(part) for part in requested_time.split(":", 1))
    except ValueError:
        return None
    today = datetime.now(_MELBOURNE_TZ).date()
    local_dt = datetime(today.year, today.month, today.day, hour, minute, tzinfo=_MELBOURNE_TZ)
    return local_dt.astimezone(timezone.utc).isoformat()


async def find_next_service(stations: ResolvedStations, requested_time: str | None = None) -> NextServiceResult:
    params = {"from": stations.from_station_name, "to": stations.to_station_name}
    after = _after_param(requested_time)
    if after is not None:
        params["after"] = after

    async with _client() as client:
        response = await client.get(f"{_base_url()}/api/next-service", params=params)

    if response.status_code == 404:
        detail = response.json()["detail"]
        raise UnknownStation(detail.get("message", "unknown station"))
    if response.status_code == 503:
        raise ScheduleUnavailable(response.json().get("detail", "schedule unavailable"))
    response.raise_for_status()
    return NextServiceResult.model_validate(response.json())
