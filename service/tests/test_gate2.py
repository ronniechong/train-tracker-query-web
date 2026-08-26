import json

import pytest

from src.pipeline import gate2
from src.pipeline.gate2 import ClarificationNeeded, ExtractedQuery, resolve_stations
from src.pipeline.models import FallbackReason
from src.pipeline.stations_cache import Route, Station

_BELGRAVE = Route(route_id="belgrave", short_name="Belgrave", long_name="Belgrave - City")
_ALAMEIN = Route(route_id="alamein", short_name="Alamein", long_name="Alamein - City")

# Real station names are always unique (verified live against train-tracker's
# API) — ambiguity comes from distinct names that both fuzzy-match a bare
# spoken word, not from two stations sharing one literal name.
_RICHMOND_BELGRAVE = Station(
    station_id="richmond-belgrave", name="Richmond Railway Station", routes=[_BELGRAVE]
)
_RICHMOND_ALAMEIN = Station(
    station_id="richmond-alamein", name="North Richmond Railway Station", routes=[_ALAMEIN]
)
_FLINDERS = Station(
    station_id="flinders", name="Flinders Street Railway Station", routes=[_BELGRAVE, _ALAMEIN]
)

_STATIONS = [_RICHMOND_BELGRAVE, _RICHMOND_ALAMEIN, _FLINDERS]

# Captured before the autouse fixture below replaces the module attribute,
# so tests exercising the real implementation directly aren't shadowed by
# the default "no suggestion" mock every other test relies on.
_real_suggest_closest_station = gate2._suggest_closest_station


@pytest.fixture(autouse=True)
def _mock_stations(monkeypatch):
    async def fake_get_stations():
        return _STATIONS

    monkeypatch.setattr("src.pipeline.gate2.get_stations", fake_get_stations)


@pytest.fixture(autouse=True)
def _no_llm_suggestion_by_default(monkeypatch):
    # Every no-match case now consults an LLM suggestion step (see
    # test_llm_suggestion_*) — default it to "no suggestion" so tests
    # that don't care about that behaviour don't make a live call.
    async def fake_suggest(spoken_name, stations, **_kwargs):
        return None

    monkeypatch.setattr("src.pipeline.gate2._suggest_closest_station", fake_suggest)


async def test_confident_single_match_resolves():
    extracted = ExtractedQuery(
        from_station="Flinders Street", to_station="Richmond", route_hint="Belgrave", time=None
    )
    result = await resolve_stations(extracted)
    assert result.from_station_id == "flinders"
    assert result.to_station_id == "richmond-belgrave"


async def test_exact_name_match_wins_over_sibling_word_subset_matches():
    # "Richmond" word-subset-matches "North Richmond" too, but an exact
    # normalized match should never be treated as ambiguous just because
    # a sibling station's name happens to contain it as a substring —
    # this is what makes confirming a disambiguated station name (from
    # the "which one did you mean?" clarification) actually resolve
    # instead of looping back into the same ambiguity.
    extracted = ExtractedQuery(from_station="Flinders Street", to_station="Richmond", route_hint=None, time=None)
    result = await resolve_stations(extracted)
    assert result.to_station_id == "richmond-belgrave"


async def test_ambiguous_name_without_route_hint_raises_clarification(monkeypatch):
    east_richmond = Station(
        station_id="richmond-east", name="East Richmond Railway Station", routes=[_BELGRAVE]
    )

    async def fake_get_stations():
        return [_RICHMOND_ALAMEIN, east_richmond, _FLINDERS]

    monkeypatch.setattr("src.pipeline.gate2.get_stations", fake_get_stations)

    extracted = ExtractedQuery(from_station="Flinders Street", to_station="Richmond", route_hint=None, time=None)
    with pytest.raises(ClarificationNeeded) as exc_info:
        await resolve_stations(extracted)
    assert exc_info.value.reason is FallbackReason.AMBIGUOUS_STATION
    assert exc_info.value.field == "to"
    assert exc_info.value.suggested_station_name is None
    assert exc_info.value.options == ["East Richmond Railway Station", "North Richmond Railway Station"]


async def test_route_hint_narrows_ambiguous_match(monkeypatch):
    east_richmond = Station(
        station_id="richmond-east", name="East Richmond Railway Station", routes=[_BELGRAVE]
    )

    async def fake_get_stations():
        return [_RICHMOND_ALAMEIN, east_richmond, _FLINDERS]

    monkeypatch.setattr("src.pipeline.gate2.get_stations", fake_get_stations)

    extracted = ExtractedQuery(
        from_station="Flinders Street", to_station="Richmond", route_hint="Alamein", time=None
    )
    result = await resolve_stations(extracted)
    assert result.to_station_id == "richmond-alamein"


async def test_low_confidence_match_raises_clarification():
    extracted = ExtractedQuery(
        from_station="Flinders Street", to_station="Xylophonia", route_hint=None, time=None
    )
    with pytest.raises(ClarificationNeeded) as exc_info:
        await resolve_stations(extracted)
    assert exc_info.value.reason is FallbackReason.LOW_CONFIDENCE_STATION


async def test_missing_station_raises_clarification():
    extracted = ExtractedQuery(from_station="Flinders Street", to_station=None, route_hint=None, time=None)
    with pytest.raises(ClarificationNeeded) as exc_info:
        await resolve_stations(extracted)
    assert exc_info.value.reason is FallbackReason.LOW_CONFIDENCE_STATION


async def test_bare_partial_name_matches_full_station_name():
    extracted = ExtractedQuery(from_station="Flinders", to_station="Richmond", route_hint="Belgrave", time=None)
    result = await resolve_stations(extracted)
    assert result.from_station_id == "flinders"


async def test_matching_is_case_insensitive():
    extracted = ExtractedQuery(
        from_station="flinders street", to_station="richmond", route_hint="belgrave", time=None
    )
    result = await resolve_stations(extracted)
    assert result.from_station_id == "flinders"


async def test_generic_station_word_is_ignored():
    extracted = ExtractedQuery(
        from_station="Flinders station", to_station="Richmond", route_hint="Belgrave", time=None
    )
    result = await resolve_stations(extracted)
    assert result.from_station_id == "flinders"


async def test_severe_stt_mishear_of_uncommon_name_still_matches(monkeypatch):
    # "Mooroolbark" transcribed by Whisper as "Morrowbark" in live testing
    # (with the STT prompt's help) — regression guard for the threshold
    # needing to stay low enough to catch this while still excluding
    # coincidental overlaps between unrelated real stations (see below).
    mooroolbark = Station(station_id="mooroolbark", name="Mooroolbark Railway Station", routes=[_BELGRAVE])

    async def fake_get_stations():
        return [*_STATIONS, mooroolbark]

    monkeypatch.setattr("src.pipeline.gate2.get_stations", fake_get_stations)
    extracted = ExtractedQuery(
        from_station="Morrowbark", to_station="Richmond", route_hint="Belgrave", time=None
    )
    result = await resolve_stations(extracted)
    assert result.from_station_id == "mooroolbark"


async def test_coincidental_fuzzy_overlap_does_not_falsely_match():
    # "Flinders" vs "Richmond" share no words and aren't a plausible STT
    # mishear of each other — regression guard for the bug where
    # lowercasing before scoring pushed some unrelated station-name pairs
    # (e.g. real stations "Richmond"/"Ormond") above the match threshold.
    extracted = ExtractedQuery(from_station="Ormond", to_station="Flinders", route_hint=None, time=None)
    with pytest.raises(ClarificationNeeded) as exc_info:
        await resolve_stations(extracted)
    assert exc_info.value.reason is FallbackReason.LOW_CONFIDENCE_STATION


async def test_llm_suggestion_offered_as_did_you_mean(monkeypatch):
    # When no string-based match exists at all (e.g. a severe mishear
    # like "Murubak" for "Mooroolbark", too mangled for any fuzzy
    # threshold), an LLM fallback may suggest a station — but only ever
    # as a question the user must confirm, never a silent resolution.
    async def fake_suggest(spoken_name, stations, **_kwargs):
        return _FLINDERS

    monkeypatch.setattr("src.pipeline.gate2._suggest_closest_station", fake_suggest)
    extracted = ExtractedQuery(from_station="Xylophonia", to_station="Richmond", route_hint="Belgrave", time=None)
    with pytest.raises(ClarificationNeeded) as exc_info:
        await resolve_stations(extracted)
    assert exc_info.value.reason is FallbackReason.LOW_CONFIDENCE_STATION
    assert "did you mean Flinders Street Railway Station" in exc_info.value.message
    assert exc_info.value.field == "from"
    assert exc_info.value.suggested_station_name == "Flinders Street Railway Station"


async def test_no_llm_suggestion_falls_back_to_generic_message():
    extracted = ExtractedQuery(
        from_station="Xylophonia", to_station="Richmond", route_hint="Belgrave", time=None
    )
    with pytest.raises(ClarificationNeeded) as exc_info:
        await resolve_stations(extracted)
    assert "did you mean" not in exc_info.value.message
    assert "couldn't find a matching station" in exc_info.value.message


class _FakeMessage:
    def __init__(self, content):
        self.content = content


class _FakeChoice:
    def __init__(self, content):
        self.message = _FakeMessage(content)


class _FakeResponse:
    def __init__(self, content):
        self.choices = [_FakeChoice(content)]


class _FakeCompletions:
    def __init__(self, content):
        self._content = content

    async def create(self, **kwargs):
        return _FakeResponse(self._content)


class _FakeChat:
    def __init__(self, content):
        self.completions = _FakeCompletions(content)


class _FakeClient:
    def __init__(self, content):
        self.chat = _FakeChat(content)


async def test_suggest_closest_station_returns_matched_station(monkeypatch):
    monkeypatch.setattr(
        gate2, "_get_client", lambda: _FakeClient(json.dumps({"best_guess": "Flinders Street Railway Station"}))
    )
    result = await _real_suggest_closest_station("murubak", _STATIONS)
    assert result is _FLINDERS


async def test_suggest_closest_station_returns_none_when_llm_declines(monkeypatch):
    monkeypatch.setattr(gate2, "_get_client", lambda: _FakeClient(json.dumps({"best_guess": "NONE"})))
    result = await _real_suggest_closest_station("asdf qwerty", _STATIONS)
    assert result is None
