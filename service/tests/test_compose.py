import pytest

from src.pipeline import compose
from src.pipeline.next_service import Leg, NextServiceResult, StationRef

_RICHMOND = StationRef(station_id="richmond-1", name="Richmond Railway Station")
_FLINDERS = StationRef(station_id="flinders-1", name="Flinders Street Railway Station")

_RESULT = NextServiceResult(
    from_station=_RICHMOND,
    to_station=_FLINDERS,
    generated_at="2026-08-26T08:00:00Z",
    reason=None,
    legs=[
        Leg(
            trip_id="t1",
            route_id="r1",
            headsign="Flinders Street via City Loop",
            from_station=_RICHMOND,
            departure_time="2026-08-26T03:08:00Z",
            to_station=_FLINDERS,
            arrival_time="2026-08-26T03:21:00Z",
        )
    ],
)


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


def _mock_client(monkeypatch, content):
    monkeypatch.setattr(compose, "_get_client", lambda: _FakeClient(content))


async def test_uses_llm_answer_when_within_budget(monkeypatch):
    _mock_client(monkeypatch, "Next train to Flinders Street leaves Richmond at 1:08 PM.")
    answer = await compose.compose_answer(_RESULT)
    assert answer == "Next train to Flinders Street leaves Richmond at 1:08 PM."


async def test_falls_back_when_llm_answer_exceeds_budget(monkeypatch):
    _mock_client(monkeypatch, "x" * 200)
    answer = await compose.compose_answer(_RESULT)
    assert len(answer) <= compose._CHARACTER_BUDGET
    assert "Richmond Railway Station" in answer


async def test_falls_back_when_llm_answer_empty(monkeypatch):
    _mock_client(monkeypatch, "")
    answer = await compose.compose_answer(_RESULT)
    assert len(answer) <= compose._CHARACTER_BUDGET
    assert "Flinders Street Railway Station" in answer


async def test_answer_never_exceeds_character_budget(monkeypatch):
    _mock_client(monkeypatch, "Next train to Flinders Street leaves Richmond at 1:08 PM.")
    answer = await compose.compose_answer(_RESULT)
    assert len(answer) <= compose._CHARACTER_BUDGET


async def test_facts_include_platform_when_present():
    result = _RESULT.model_copy(deep=True)
    result.legs[0].from_platform_code = "8"
    facts = compose._facts(result)
    assert "platform 8" in facts


async def test_facts_omit_platform_when_absent():
    facts = compose._facts(_RESULT)
    assert "platform" not in facts


async def test_fallback_answer_includes_platform_when_present():
    result = _RESULT.model_copy(deep=True)
    result.legs[0].from_platform_code = "8"
    answer = compose._fallback_answer(result)
    assert "platform 8" in answer
