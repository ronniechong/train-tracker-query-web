import pytest

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


@pytest.fixture(autouse=True)
def _mock_stations(monkeypatch):
    async def fake_get_stations():
        return _STATIONS

    monkeypatch.setattr("src.pipeline.gate2.get_stations", fake_get_stations)


async def test_confident_single_match_resolves():
    extracted = ExtractedQuery(
        from_station="Flinders Street", to_station="Richmond", route_hint="Belgrave", time=None
    )
    result = await resolve_stations(extracted)
    assert result.from_station_id == "flinders"
    assert result.to_station_id == "richmond-belgrave"


async def test_ambiguous_name_without_route_hint_raises_clarification():
    extracted = ExtractedQuery(from_station="Flinders Street", to_station="Richmond", route_hint=None, time=None)
    with pytest.raises(ClarificationNeeded) as exc_info:
        await resolve_stations(extracted)
    assert exc_info.value.reason is FallbackReason.AMBIGUOUS_STATION


async def test_route_hint_narrows_ambiguous_match():
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
