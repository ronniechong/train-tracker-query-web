import json

from groq import AsyncGroq
from pydantic import BaseModel
from rapidfuzz import fuzz

from .models import FallbackReason
from .stations_cache import Station, get_stations

_EXTRACTION_MODEL = "openai/gpt-oss-20b"

# Below this fuzzy-match score (rapidfuzz WRatio, 0-100), treat the name as
# not confidently matched at all rather than guessing. Pre-committed,
# revisit once Milestone 03's eval set gives real precision/recall data.
_LOW_CONFIDENCE_THRESHOLD = 70
_ROUTE_HINT_THRESHOLD = 70

_EXTRACTION_SYSTEM_PROMPT = (
    "Extract the origin station, destination station, an optional line/"
    "route name if one is explicitly mentioned, and an optional time if "
    "one is explicitly mentioned, from a transcript of a spoken train-"
    "schedule question. Use null for anything not stated. Do not guess or "
    "normalize station names beyond what was said."
)

_EXTRACTION_SCHEMA = {
    "type": "object",
    "properties": {
        "from_station": {"type": ["string", "null"]},
        "to_station": {"type": ["string", "null"]},
        "route_hint": {"type": ["string", "null"]},
        "time": {"type": ["string", "null"]},
    },
    "required": ["from_station", "to_station", "route_hint", "time"],
    "additionalProperties": False,
}

_client: AsyncGroq | None = None


def _get_client() -> AsyncGroq:
    global _client
    if _client is None:
        _client = AsyncGroq()
    return _client


class ExtractedQuery(BaseModel):
    from_station: str | None
    to_station: str | None
    route_hint: str | None
    time: str | None


class ResolvedStations(BaseModel):
    from_station_id: str
    from_station_name: str
    to_station_id: str
    to_station_name: str


class ClarificationNeeded(Exception):
    def __init__(self, message: str, reason: FallbackReason) -> None:
        super().__init__(message)
        self.message = message
        self.reason = reason


async def extract(transcript: str) -> ExtractedQuery:
    response = await _get_client().chat.completions.create(
        model=_EXTRACTION_MODEL,
        temperature=0,
        messages=[
            {"role": "system", "content": _EXTRACTION_SYSTEM_PROMPT},
            {"role": "user", "content": transcript},
        ],
        response_format={
            "type": "json_schema",
            "json_schema": {"name": "extraction", "schema": _EXTRACTION_SCHEMA, "strict": True},
        },
    )
    return ExtractedQuery.model_validate_json(response.choices[0].message.content)


def _match_candidates(name: str, stations: list[Station]) -> list[tuple[Station, float]]:
    scored = [(s, fuzz.WRatio(name, s.name)) for s in stations]
    return [(s, score) for s, score in scored if score >= _LOW_CONFIDENCE_THRESHOLD]


def _narrow_by_route_hint(
    candidates: list[tuple[Station, float]], route_hint: str | None
) -> list[tuple[Station, float]]:
    if route_hint is None:
        return candidates
    narrowed = [
        (station, score)
        for station, score in candidates
        if any(
            fuzz.WRatio(route_hint, route.short_name) >= _ROUTE_HINT_THRESHOLD
            or fuzz.WRatio(route_hint, route.long_name) >= _ROUTE_HINT_THRESHOLD
            for route in station.routes
        )
    ]
    return narrowed or candidates


def _resolve_one(spoken_name: str | None, stations: list[Station], route_hint: str | None) -> Station:
    if spoken_name is None:
        raise ClarificationNeeded(
            "I didn't catch a station name — try asking again.",
            FallbackReason.LOW_CONFIDENCE_STATION,
        )

    candidates = _match_candidates(spoken_name, stations)
    if not candidates:
        raise ClarificationNeeded(
            f"I heard '{spoken_name}' but couldn't find a matching station — try asking again.",
            FallbackReason.LOW_CONFIDENCE_STATION,
        )

    narrowed = _narrow_by_route_hint(candidates, route_hint)
    if len(narrowed) > 1:
        options = ", ".join(sorted({s.name for s, _ in narrowed}))
        raise ClarificationNeeded(
            f"There are a few stations matching '{spoken_name}' ({options}) — "
            "which line are you near?",
            FallbackReason.AMBIGUOUS_STATION,
        )

    best_station, _ = narrowed[0]
    return best_station


async def resolve_stations(extracted: ExtractedQuery) -> ResolvedStations:
    stations = await get_stations()
    from_station = _resolve_one(extracted.from_station, stations, extracted.route_hint)
    to_station = _resolve_one(extracted.to_station, stations, extracted.route_hint)
    return ResolvedStations(
        from_station_id=from_station.station_id,
        from_station_name=from_station.name,
        to_station_id=to_station.station_id,
        to_station_name=to_station.name,
    )
