import json

from groq import AsyncGroq
from pydantic import BaseModel
from rapidfuzz import fuzz

from .models import FallbackReason
from .stations_cache import Station, get_stations

_EXTRACTION_MODEL = "openai/gpt-oss-20b"

# A spoken name that's an exact word-subset of a station's name (e.g.
# "Flinders" for "Flinders Street") is always a confident match — see
# _is_word_subset. Anything else falls back to fuzzy scoring, which needs
# a stricter bar: short station names can coincidentally fuzzy-match each
# other well above 70 (e.g. "Richmond" vs. "Ormond" scored 71.4, two real
# but unrelated stations) without being an actual STT mishear. Both
# pre-committed, revisit once Milestone 03's eval set gives real
# precision/recall data.
_FUZZY_MISHEAR_THRESHOLD = 80
_ROUTE_HINT_THRESHOLD = 70

# Every station name shares this suffix, which otherwise inflates fuzzy
# scores enough to make unrelated stations look like ambiguous matches
# (e.g. "North Melbourne" vs. "Melbourne Central").
_NAME_SUFFIX = " railway station"

# Generic words people add when speaking a station name ("Flinders
# station", "the Richmond stop") that carry no distinguishing
# information, since every candidate is a station — stripped from both
# sides so they never cost a match.
_STOPWORDS = {"station", "stations", "the"}


def _normalize(name: str) -> str:
    n = name.lower().strip()
    if n.endswith(_NAME_SUFFIX):
        n = n[: -len(_NAME_SUFFIX)]
    words = [w for w in n.split() if w not in _STOPWORDS]
    return " ".join(words)


def _is_word_subset(spoken: str, candidate: str) -> bool:
    spoken_words = set(spoken.split())
    return bool(spoken_words) and spoken_words.issubset(set(candidate.split()))

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


def _is_confident_match(spoken: str, candidate: str) -> bool:
    if _is_word_subset(spoken, candidate):
        return True
    return fuzz.token_sort_ratio(spoken, candidate) >= _FUZZY_MISHEAR_THRESHOLD


def _match_candidates(name: str, stations: list[Station]) -> list[Station]:
    normalized_name = _normalize(name)
    return [s for s in stations if _is_confident_match(normalized_name, _normalize(s.name))]


def _narrow_by_route_hint(candidates: list[Station], route_hint: str | None) -> list[Station]:
    if route_hint is None:
        return candidates
    normalized_hint = route_hint.lower().strip()
    narrowed = [
        station
        for station in candidates
        if any(
            fuzz.WRatio(normalized_hint, route.short_name.lower()) >= _ROUTE_HINT_THRESHOLD
            or fuzz.WRatio(normalized_hint, route.long_name.lower()) >= _ROUTE_HINT_THRESHOLD
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
        options = ", ".join(sorted({s.name for s in narrowed}))
        raise ClarificationNeeded(
            f"There are a few stations matching '{spoken_name}' ({options}) — "
            "which line are you near?",
            FallbackReason.AMBIGUOUS_STATION,
        )

    return narrowed[0]


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
