import os
import time

import httpx
from pydantic import BaseModel

_CACHE_TTL_SECONDS = 60 * 60


class Route(BaseModel):
    route_id: str
    short_name: str
    long_name: str


class Station(BaseModel):
    station_id: str
    name: str
    routes: list[Route]


class ScheduleUnavailable(Exception):
    """train-tracker has no static snapshot pinned for today (transient)."""


_cached_stations: list[Station] | None = None
_cached_at: float = 0.0


def _base_url() -> str:
    base_url = os.environ["TRAIN_TRACKER_API_BASE_URL"]
    return base_url.rstrip("/")


async def get_stations() -> list[Station]:
    global _cached_stations, _cached_at

    if _cached_stations is not None and time.monotonic() - _cached_at < _CACHE_TTL_SECONDS:
        return _cached_stations

    async with httpx.AsyncClient() as client:
        response = await client.get(f"{_base_url()}/api/stations")

    if response.status_code == 503:
        raise ScheduleUnavailable(response.json().get("detail", "schedule unavailable"))
    response.raise_for_status()

    stations = [Station.model_validate(s) for s in response.json()["stations"]]
    _cached_stations = stations
    _cached_at = time.monotonic()
    return stations
