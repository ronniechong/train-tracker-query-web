import os

import httpx
from pydantic import BaseModel

from .gate2 import ResolvedStations
from .stations_cache import ScheduleUnavailable


class StationRef(BaseModel):
    station_id: str
    name: str


class Leg(BaseModel):
    trip_id: str
    route_id: str
    headsign: str
    from_station: StationRef
    departure_time: str
    to_station: StationRef
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


async def find_next_service(stations: ResolvedStations) -> NextServiceResult:
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{_base_url()}/api/next-service",
            params={"from": stations.from_station_name, "to": stations.to_station_name},
        )

    if response.status_code == 404:
        detail = response.json()["detail"]
        raise UnknownStation(detail.get("message", "unknown station"))
    if response.status_code == 503:
        raise ScheduleUnavailable(response.json().get("detail", "schedule unavailable"))
    response.raise_for_status()
    return NextServiceResult.model_validate(response.json())
