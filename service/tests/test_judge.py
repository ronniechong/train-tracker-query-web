import json

from src.pipeline import judge


class _FakeMessage:
    def __init__(self, content):
        self.content = content


class _FakeChoice:
    def __init__(self, content):
        self.message = _FakeMessage(content)


class _FakeResponse:
    def __init__(self, content):
        self.choices = [_FakeChoice(content)]
        self.usage = None


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


async def test_grade_parses_verdict(monkeypatch):
    content = json.dumps(
        {"accuracy_pass": True, "tone_pass": True, "length_pass": False, "notes": "a bit long"}
    )
    monkeypatch.setattr(judge, "_get_client", lambda: _FakeClient(content))
    verdict = await judge.grade("success", {"from_station": "Richmond"}, "Catch the 5:30pm...")
    assert verdict.accuracy_pass is True
    assert verdict.length_pass is False
    assert verdict.overall_pass is False


async def test_overall_pass_requires_all_three():
    verdict = judge.JudgeVerdict(accuracy_pass=True, tone_pass=True, length_pass=True, notes="")
    assert verdict.overall_pass is True


def test_prompt_tells_judge_time_field_is_a_lower_bound():
    # Live-verified regression (2026-08-27): a correct answer with
    # departure 18:22 was marked accuracy_pass=False against an
    # expected_fields.time of 18:15 - the judge treated it as an exact
    # expected departure rather than the "next train at or after this
    # time" filter it actually is.
    assert "AT OR AFTER" in judge._JUDGE_SYSTEM_PROMPT


def test_prompt_tells_judge_schedule_details_are_not_expected_fields():
    # Live-verified regression (2026-08-27): a correct answer including a
    # real departure time and platform (from a live schedule lookup) was
    # marked accuracy_pass=False for "inventing information not in
    # expected fields" - the judge had no way to know expected_fields is
    # only the query's extracted intent, not the schedule itself.
    assert "NOT expected to appear in\nexpected_fields" in judge._JUDGE_SYSTEM_PROMPT or (
        "not expected to appear in expected_fields" in judge._JUDGE_SYSTEM_PROMPT.lower()
    )
