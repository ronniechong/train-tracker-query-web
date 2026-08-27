import pytest

from src.pipeline import tracing
from src.pipeline.gate2 import ExtractedQuery


def test_safe_query_summary_never_includes_raw_transcript():
    extracted = ExtractedQuery(
        from_station="Richmond",
        to_station="Flinders Street",
        route_hint=None,
        time=None,
    )
    summary = tracing.safe_query_summary(extracted, transcript_length=42)

    assert summary == {
        "transcript_length": 42,
        "from_station": "Richmond",
        "to_station": "Flinders Street",
        "route_hint": None,
        "time": None,
    }
    assert "transcript" not in summary


def test_safe_query_summary_handles_missing_extraction():
    assert tracing.safe_query_summary(None, transcript_length=10) == {"transcript_length": 10}


def test_chat_cost_usd_unknown_model_is_free():
    assert tracing.chat_cost_usd("some-unpriced-model", 1_000_000) == 0.0


def test_chat_cost_usd_known_model():
    cost = tracing.chat_cost_usd("openai/gpt-oss-20b", 1_000_000)
    assert cost == pytest.approx(0.10)


def test_record_chat_cost_defaults_to_zero_when_usage_missing():
    class _NoUsageResponse:
        pass

    # Must not raise even though the response has no `.usage` attribute
    # (real API edge cases, and most test fakes elsewhere in this suite).
    tracing.record_chat_cost(None, "openai/gpt-oss-20b", _NoUsageResponse())


def test_daily_spend_cap_triggers_after_enough_recorded_cost(monkeypatch):
    monkeypatch.setattr(tracing, "_daily_spend_usd", 0.0)
    monkeypatch.setattr(tracing, "_daily_spend_date", None)
    monkeypatch.setattr(tracing, "_alerted_today", False)

    assert not tracing.is_over_daily_cap()
    tracing._record_spend(tracing._DAILY_SPEND_CAP_USD)
    assert tracing.is_over_daily_cap()


def test_tts_cost_usd_scales_with_character_count():
    assert tracing.tts_cost_usd(1_000_000) == pytest.approx(22.0)
    assert tracing.tts_cost_usd(0) == 0.0


def test_record_feedback_is_noop_when_tracing_unconfigured(monkeypatch):
    monkeypatch.setattr(tracing, "_get_client", lambda: None)
    # Must not raise even with no real trace to attach to.
    tracing.record_feedback("some-trace-id", True)


def test_record_feedback_creates_boolean_score_on_the_trace(monkeypatch):
    calls = []

    class _FakeClient:
        def create_score(self, **kwargs):
            calls.append(kwargs)

        def flush(self):
            pass

    monkeypatch.setattr(tracing, "_get_client", lambda: _FakeClient())
    tracing.record_feedback("trace-123", False)

    assert len(calls) == 1
    assert calls[0]["trace_id"] == "trace-123"
    assert calls[0]["value"] is False
    assert calls[0]["data_type"] == "BOOLEAN"
