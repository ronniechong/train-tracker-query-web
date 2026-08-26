import os
from contextlib import contextmanager
from datetime import UTC, datetime
from logging import getLogger
from typing import TYPE_CHECKING

from langfuse import Langfuse

if TYPE_CHECKING:
    # Only needed for the type hint below; a real (non-TYPE_CHECKING) import
    # here creates a circular import with gate2, which imports this module.
    from .gate2 import ExtractedQuery

_logger = getLogger(__name__)

# $10/day cap, alert at 75% — addendum-02 Note B. In-memory only: resets on
# restart and isn't shared across processes. That's an accepted gap for
# this milestone (basic caps only); Milestone 04 is where caps get
# hardened into something that survives a restart / multiple workers.
_DAILY_SPEND_CAP_USD = 10.0
_DAILY_SPEND_ALERT_RATIO = 0.75

# Approximate, from Groq's published per-model rates at the time addendum-02
# was priced (2026-07-20) — good enough for trend/cap monitoring, not
# billing-accurate. Revisit against Groq's live pricing page if spend
# trends look off.
_CHAT_MODEL_USD_PER_1M_TOKENS = {
    "openai/gpt-oss-20b": 0.10,
    "meta-llama/llama-prompt-guard-2-86m": 0.04,
    "llama-3.3-70b-versatile": 0.59,
}
_TTS_USD_PER_1M_CHARS = 22.0
# Whisper Large v3 Turbo is priced per second of audio; audio duration
# isn't cheaply available from raw bytes without decoding, so this is a
# flat per-query estimate rather than a real per-second calculation.
_STT_USD_PER_QUERY_ESTIMATE = 0.0006

_daily_spend_usd = 0.0
_daily_spend_date: str | None = None
_alerted_today = False


def _today_key() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d")


def _record_spend(usd: float) -> None:
    global _daily_spend_usd, _daily_spend_date, _alerted_today
    today = _today_key()
    if today != _daily_spend_date:
        _daily_spend_date = today
        _daily_spend_usd = 0.0
        _alerted_today = False

    _daily_spend_usd += usd
    ratio = _daily_spend_usd / _DAILY_SPEND_CAP_USD
    if ratio >= 1.0:
        _logger.error(
            "Daily Groq spend cap exceeded: $%.4f / $%.2f", _daily_spend_usd, _DAILY_SPEND_CAP_USD
        )
    elif ratio >= _DAILY_SPEND_ALERT_RATIO and not _alerted_today:
        _alerted_today = True
        _logger.warning(
            "Daily Groq spend at %.0f%% of cap: $%.4f / $%.2f",
            ratio * 100,
            _daily_spend_usd,
            _DAILY_SPEND_CAP_USD,
        )


def is_over_daily_cap() -> bool:
    return _daily_spend_date == _today_key() and _daily_spend_usd >= _DAILY_SPEND_CAP_USD


def chat_cost_usd(model: str, total_tokens: int) -> float:
    rate = _CHAT_MODEL_USD_PER_1M_TOKENS.get(model, 0.0)
    return (total_tokens / 1_000_000) * rate


def record_chat_cost(span, model: str, response) -> None:
    # response.usage is absent on some fakes/edge-case responses (and in
    # unit tests, which stub only the fields their assertions need) --
    # cost tracking degrades to zero rather than raising either way.
    usage = getattr(response, "usage", None)
    total_tokens = getattr(usage, "total_tokens", 0) or 0
    record_cost(span, model, chat_cost_usd(model, total_tokens))


def tts_cost_usd(char_count: int) -> float:
    return (char_count / 1_000_000) * _TTS_USD_PER_1M_CHARS


def stt_cost_usd() -> float:
    return _STT_USD_PER_QUERY_ESTIMATE


_client: Langfuse | None = None
_configured: bool | None = None


def _get_client() -> Langfuse | None:
    global _client, _configured
    if _configured is None:
        _configured = bool(
            os.environ.get("LANGFUSE_PUBLIC_KEY") and os.environ.get("LANGFUSE_SECRET_KEY")
        )
    if not _configured:
        return None
    if _client is None:
        _client = Langfuse()
    return _client


def safe_query_summary(extracted: "ExtractedQuery | None", transcript_length: int) -> dict:
    """Trace input built from structured fields only — never the raw
    transcript. Station names/times are fine to trace; the raw transcript
    can carry incidental PII (a name, a stated habit pattern) so it must
    never reach Langfuse, obfuscated or otherwise. Length is kept only as
    a debugging signal.
    """
    if extracted is None:
        return {"transcript_length": transcript_length}
    return {
        "transcript_length": transcript_length,
        "from_station": extracted.from_station,
        "to_station": extracted.to_station,
        "route_hint": extracted.route_hint,
        "time": extracted.time,
    }


@contextmanager
def trace_query(transcript_length: int):
    client = _get_client()
    if client is None:
        yield None, lambda *a, **k: None
        return

    with client.start_as_current_observation(
        as_type="span", name="voice-query", input={"transcript_length": transcript_length}
    ) as root_span:
        try:
            yield root_span, root_span.update
        finally:
            client.flush()


@contextmanager
def stage_span(name: str, **input_kwargs):
    client = _get_client()
    if client is None:
        yield None
        return

    with client.start_as_current_observation(
        as_type="span", name=name, input=input_kwargs or None
    ) as span:
        yield span


def record_cost(span, model: str, usd: float) -> None:
    _record_spend(usd)
    if span is not None:
        span.update(
            metadata={"model": model}, cost_details={"cost_amount": usd, "cost_currency": "USD"}
        )
