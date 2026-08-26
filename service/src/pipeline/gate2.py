import json

from groq import AsyncGroq
from pydantic import BaseModel
from rapidfuzz import fuzz

from . import tracing
from .models import FallbackReason
from .stations_cache import Station, get_stations

_EXTRACTION_MODEL = "openai/gpt-oss-20b"

# A spoken name that's an exact word-subset of a station's name (e.g.
# "Flinders" for "Flinders Street") is always a confident match — see
# _is_word_subset. Anything else falls back to fuzzy scoring, which needs
# a bar that separates two failure modes pulling in opposite directions:
# too low and unrelated real stations coincidentally collide (a live
# sweep of all 226 real stations found several pairs — e.g. "Armadale"/
# "Parkdale", "Caulfield"/"Upfield" — scoring exactly 75.0); too high and
# genuine severe mishears of uncommon names get rejected ("Mooroolbark"
# transcribed as "Morrowbark" scored 76.2, live-verified via a real STT
# round-trip). 76 is the gap between those two live-measured clusters.
# Pre-committed, revisit once Milestone 03's eval set gives real
# precision/recall data.
_FUZZY_MISHEAR_THRESHOLD = 76
_ROUTE_HINT_THRESHOLD = 70

# Every station name shares this suffix, which otherwise inflates fuzzy
# scores enough to make unrelated stations look like ambiguous matches
# (e.g. "North Melbourne" vs. "Melbourne Central").
_NAME_SUFFIX = " railway station"

# Generic words people add when speaking a station name ("Flinders
# station", "the Richmond stop") that carry no distinguishing
# information, since every candidate is a station — stripped from both
# sides so they never cost a match. Cardinal directions are deliberately
# NOT included here even though they're just as "generic" in isolation —
# unlike "the"/"station", they're load-bearing in real compound station
# names (East Richmond, North Melbourne, West Footscray), so stripping
# them from both sides would make "East Richmond" and "Richmond"
# normalize identically and silently destroy the disambiguation between
# them. See _BARE_DIRECTIONS below for the narrower fix this needs.
_STOPWORDS = {"station", "stations", "the"}

# A bare cardinal direction with nothing else ("next train from north to
# south") isn't a station name at all, but word-subset-matches every real
# "North "/"South "-prefixed station (North Melbourne, North Richmond, ...)
# and gets offered back as if one of those was plausibly meant. Handled
# separately from _STOPWORDS (see comment above) — only the spoken side is
# ever checked against this set, real station names are untouched.
_BARE_DIRECTIONS = {"north", "south", "east", "west"}


def _normalize(name: str) -> str:
    n = name.lower().strip()
    if n.endswith(_NAME_SUFFIX):
        n = n[: -len(_NAME_SUFFIX)]
    words = [w for w in n.split() if w not in _STOPWORDS]
    return " ".join(words)


def _is_word_subset(spoken: str, candidate: str) -> bool:
    spoken_words = set(spoken.split())
    return bool(spoken_words) and spoken_words.issubset(set(candidate.split()))

_SUGGESTION_MODEL = "openai/gpt-oss-20b"
_NO_SUGGESTION = "NONE"

# Sending all 226 real station names as a strict-JSON enum is unreliable —
# live testing found it intermittently fails generation entirely (empty
# completion, schema validation error) even with a generous token budget,
# seemingly due to the combination of enum size and punctuation-heavy real
# names. Pre-filtering to a small top-K by rough fuzzy score, and letting
# the LLM choose only among those (or decline), keeps the schema small and
# was reliable in live testing while still fully constraining the model to
# real station names — never a hallucinated one.
_SUGGESTION_CANDIDATE_COUNT = 20

_SUGGESTION_SYSTEM_PROMPT = (
    "A speech-to-text system transcribed a Melbourne train station name, "
    "but it doesn't match any real station closely enough for a plain "
    "text/fuzzy match. STT commonly mangles vowels, syllables, and word "
    "breaks in uncommon names. Given the heard text and a list of "
    "candidate station names, suggest the single one you're reasonably "
    "confident was actually meant, even if the transcription is quite "
    "different from the real spelling. Respond with the exact candidate "
    f"name, or '{_NO_SUGGESTION}' if none is a plausible match. This is "
    "only ever offered back to the user as a question — never guess if "
    "you're not reasonably confident."
)

_EXTRACTION_SYSTEM_PROMPT = (
    "Extract the origin station, destination station, an optional line/"
    "route name if one is explicitly mentioned, and an optional time if "
    "one is explicitly mentioned, from a transcript of a spoken train-"
    "schedule question. Use null for anything not stated. Do not guess or "
    "normalize station names beyond what was said. If a time is stated, "
    "normalize it to 24-hour HH:MM format (e.g. '5:30pm' -> '17:30'); "
    "assume today's date, never guess a date."
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
    def __init__(
        self,
        message: str,
        reason: FallbackReason,
        field: str,
        suggested_station_name: str | None = None,
        options: list[str] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.reason = reason
        self.field = field
        self.suggested_station_name = suggested_station_name
        self.options = options


async def extract(transcript: str, span=None) -> ExtractedQuery:
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
    tracing.record_chat_cost(span, _EXTRACTION_MODEL, response)
    return ExtractedQuery.model_validate_json(response.choices[0].message.content)


def _is_confident_match(spoken: str, candidate: str) -> bool:
    if _is_word_subset(spoken, candidate):
        return True
    return fuzz.token_sort_ratio(spoken, candidate) >= _FUZZY_MISHEAR_THRESHOLD


def _match_candidates(name: str, stations: list[Station]) -> list[Station]:
    normalized_name = _normalize(name)
    if normalized_name in _BARE_DIRECTIONS:
        return []
    # An exact normalized match always wins outright, even when the same
    # text would also word-subset-match sibling stations (e.g. "Richmond"
    # is a subset of "East Richmond" too). Without this, confirming an
    # exact station name picked from an ambiguous-match list (the "which
    # one did you mean?" clarification) re-triggers the same ambiguity
    # instead of resolving.
    exact = [s for s in stations if _normalize(s.name) == normalized_name]
    if exact:
        return exact
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


def _top_candidates(spoken_name: str, stations: list[Station]) -> list[Station]:
    normalized_name = _normalize(spoken_name)
    ranked = sorted(
        stations,
        key=lambda s: fuzz.token_sort_ratio(normalized_name, _normalize(s.name)),
        reverse=True,
    )
    return ranked[:_SUGGESTION_CANDIDATE_COUNT]


async def _suggest_closest_station(spoken_name: str, stations: list[Station], span=None) -> Station | None:
    candidates = _top_candidates(spoken_name, stations)
    by_name = {s.name: s for s in candidates}
    schema = {
        "type": "object",
        "properties": {
            "best_guess": {"type": "string", "enum": [*by_name.keys(), _NO_SUGGESTION]}
        },
        "required": ["best_guess"],
        "additionalProperties": False,
    }
    response = await _get_client().chat.completions.create(
        model=_SUGGESTION_MODEL,
        temperature=0,
        messages=[
            {"role": "system", "content": _SUGGESTION_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"Heard: {spoken_name}\n\nCandidates:\n" + "\n".join(by_name),
            },
        ],
        response_format={
            "type": "json_schema",
            "json_schema": {"name": "suggestion", "schema": schema, "strict": True},
        },
    )
    tracing.record_chat_cost(span, _SUGGESTION_MODEL, response)
    guess = json.loads(response.choices[0].message.content)["best_guess"]
    return by_name.get(guess)


async def _resolve_one(
    field: str, spoken_name: str | None, stations: list[Station], route_hint: str | None, span=None
) -> Station:
    if spoken_name is None:
        raise ClarificationNeeded(
            "I didn't catch a station name — try asking again.",
            FallbackReason.LOW_CONFIDENCE_STATION,
            field,
        )

    candidates = _match_candidates(spoken_name, stations)
    if not candidates:
        suggestion = await _suggest_closest_station(spoken_name, stations, span=span)
        if suggestion is not None:
            raise ClarificationNeeded(
                f"I heard '{spoken_name}' — did you mean {suggestion.name}?",
                FallbackReason.LOW_CONFIDENCE_STATION,
                field,
                suggested_station_name=suggestion.name,
            )
        raise ClarificationNeeded(
            f"I heard '{spoken_name}' but couldn't find a matching station — try asking again.",
            FallbackReason.LOW_CONFIDENCE_STATION,
            field,
        )

    narrowed = _narrow_by_route_hint(candidates, route_hint)
    if len(narrowed) > 1:
        option_names = sorted({s.name for s in narrowed})
        raise ClarificationNeeded(
            f"There are a few stations matching '{spoken_name}' "
            f"({', '.join(option_names)}) — which one did you mean?",
            FallbackReason.AMBIGUOUS_STATION,
            field,
            options=option_names,
        )

    return narrowed[0]


async def resolve_stations(extracted: ExtractedQuery, span=None) -> ResolvedStations:
    stations = await get_stations()
    from_station = await _resolve_one(
        "from", extracted.from_station, stations, extracted.route_hint, span=span
    )
    to_station = await _resolve_one(
        "to", extracted.to_station, stations, extracted.route_hint, span=span
    )
    return ResolvedStations(
        from_station_id=from_station.station_id,
        from_station_name=from_station.name,
        to_station_id=to_station.station_id,
        to_station_name=to_station.name,
    )
