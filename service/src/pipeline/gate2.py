from pydantic import BaseModel


class ExtractedQuery(BaseModel):
    from_station: str | None
    to_station: str | None
    route_hint: str | None
    time: str | None


class ResolvedStations(BaseModel):
    from_station_id: str
    to_station_id: str


def extract(transcript: str) -> ExtractedQuery:
    raise NotImplementedError("Gate 2 extraction not yet implemented")


def resolve_stations(extracted: ExtractedQuery) -> ResolvedStations:
    raise NotImplementedError("Gate 2 station resolution not yet implemented")
