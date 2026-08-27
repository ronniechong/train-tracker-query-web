"""Runs the three M03 eval sets (extraction, STT mishear, end-to-end) plus
judge grading against the real, live pipeline. Hits Groq and train-tracker's
API - never run as part of normal CI (see the "eval" pytest marker). Trigger
manually: `pytest -m eval`.
"""

import json
from pathlib import Path
from unittest import mock

from src.pipeline import gate2, judge as judge_module, orchestrator, tracing
from src.pipeline.gate2 import ClarificationNeeded
from src.pipeline.models import FallbackReason
from src.pipeline.stations_cache import get_stations

_EVAL_DIR = Path(__file__).parent


def _load(name: str) -> list[dict]:
    return json.loads((_EVAL_DIR / name).read_text())


def load_extraction_golden() -> list[dict]:
    return _load("extraction_golden.json")


def load_stt_mishear() -> list[dict]:
    return _load("stt_mishear.json")


def load_end_to_end() -> list[dict]:
    return _load("end_to_end.json")


async def run_extraction_case(case: dict) -> tuple[bool, dict]:
    """Returns (matched, actual_fields)."""
    extracted = await gate2.extract(case["transcript"])
    actual = extracted.model_dump()
    return actual == case["expected"], actual


async def run_mishear_case(case: dict) -> tuple[bool, str]:
    """Returns (matched, actual_outcome). See stt_mishear.json's
    expected_outcome values: confident_match, ambiguous_options,
    no_match_fallback. A suggestion offered by the LLM-suggestion path
    also satisfies "no_match_fallback" - it degrades to a clarification
    rather than a silent wrong-station answer, same as an outright
    no-match (see stt_mishear.json's own case notes)."""
    stations = await get_stations()
    try:
        station = await gate2._resolve_one("from", case["spoken"], stations, None)
        actual = "confident_match"
        matched = actual == case["expected_outcome"] and [station.name] == case["expected_station_names"]
        return matched, actual
    except ClarificationNeeded as exc:
        if exc.reason == FallbackReason.AMBIGUOUS_STATION:
            actual = "ambiguous_options"
            matched = actual == case["expected_outcome"] and sorted(exc.options or []) == sorted(
                case["expected_station_names"]
            )
        elif exc.suggested_station_name:
            actual = "suggestion_offered"
            matched = case["expected_outcome"] == "no_match_fallback"
        else:
            actual = "no_match_fallback"
            matched = actual == case["expected_outcome"]
        return matched, actual


def classify_outcome(resp) -> str:
    """A clarification only counts as "clarification" if it offers
    something actionable (options or a suggested station) - otherwise
    it's functionally a fallback (nothing for the user to act on), even
    though the response model always wraps it in ClarificationInfo. See
    end_to_end.json's north/south case note for the live-verified case
    that established this."""
    reason = resp.fallback_reason
    if reason is None:
        return "success"
    if reason in (FallbackReason.OFF_TOPIC, FallbackReason.NO_SERVICE_TODAY, FallbackReason.NO_ROUTE_FOUND):
        return "fallback"
    if reason in (FallbackReason.AMBIGUOUS_STATION, FallbackReason.UNKNOWN_STATION):
        return "clarification"
    if reason == FallbackReason.LOW_CONFIDENCE_STATION:
        c = resp.clarification
        if c and (c.options or c.suggested_station_name):
            return "clarification"
        return "fallback"
    return "unknown"


async def run_end_to_end_case(case: dict) -> tuple[bool, "object"]:
    """Returns (matched, response). TTS is force-skipped (is_over_daily_cap
    patched to True) - these sets test text/outcome accuracy, not audio,
    per the milestone's transcript-only eval scoping."""
    with mock.patch.object(tracing, "is_over_daily_cap", return_value=True):
        resp = await orchestrator.run_pipeline_for_transcript(case["transcript"])
    matched = classify_outcome(resp) == case["expected_category"]
    return matched, resp


async def grade_end_to_end_case(case: dict, resp) -> "judge_module.JudgeVerdict":
    return await judge_module.grade(case["expected_category"], case["expected_fields"], resp.text)
