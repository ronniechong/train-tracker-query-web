from . import compose, declines, gate1, gate2, next_service, stt, tracing, tts
from .errors import UpstreamUnavailable
from .gate1 import Gate1Outcome
from .gate2 import ClarificationNeeded, ExtractedQuery
from .models import ClarificationInfo, ExtractedQueryFields, FallbackReason, QueryResponse
from .next_service import UnknownStation

_PTV_JOURNEY_PLANNER_URL = "https://www.ptv.vic.gov.au/journey"

# Shared across "over the daily Groq spend cap" and "an upstream Groq call
# failed with no graceful degrade available" - the end user doesn't need
# to distinguish the cause; operators still can, via logs and the trace's
# fallback_reason.
_SERVICE_UNAVAILABLE_MESSAGE = (
    "Sorry, I'm having trouble answering right now — please try again in a moment."
)


def _service_unavailable_response() -> QueryResponse:
    return QueryResponse(
        text=_SERVICE_UNAVAILABLE_MESSAGE, fallback_reason=FallbackReason.SERVICE_UNAVAILABLE
    )


async def run_pipeline(audio_bytes: bytes) -> QueryResponse:
    if tracing.is_over_daily_cap():
        return _service_unavailable_response()
    with tracing.trace_query(len(audio_bytes)) as (trace_span, update_trace, trace_id):
        try:
            with tracing.stage_span("stt") as span:
                transcript = await stt.transcribe(audio_bytes, span=span)
            response = await _run_pipeline_for_transcript(transcript, trace_span, update_trace)
        except UpstreamUnavailable:
            update_trace(output={"fallback_reason": FallbackReason.SERVICE_UNAVAILABLE})
            return _service_unavailable_response()
        response.trace_id = trace_id
        return response


async def run_pipeline_for_transcript(transcript: str) -> QueryResponse:
    if tracing.is_over_daily_cap():
        return _service_unavailable_response()
    with tracing.trace_query(len(transcript)) as (trace_span, update_trace, trace_id):
        try:
            response = await _run_pipeline_for_transcript(transcript, trace_span, update_trace)
        except UpstreamUnavailable:
            update_trace(output={"fallback_reason": FallbackReason.SERVICE_UNAVAILABLE})
            return _service_unavailable_response()
        response.trace_id = trace_id
        return response


async def _run_pipeline_for_transcript(transcript: str, trace_span, update_trace) -> QueryResponse:
    with tracing.stage_span("gate1") as span:
        gate1_outcome = await gate1.check(transcript, span=span)
    if gate1_outcome is not Gate1Outcome.PASS:
        update_trace(output={"fallback_reason": FallbackReason.OFF_TOPIC})
        return QueryResponse(
            text=declines.random_decline(),
            fallback_reason=FallbackReason.OFF_TOPIC,
        )

    with tracing.stage_span("gate2-extract") as span:
        extracted = await gate2.extract(transcript, span=span)
    # Only structured fields ever reach the trace — never the raw
    # transcript, which can carry incidental PII (a name, a stated habit
    # pattern) even though the query itself is just station names/times.
    update_trace(input=tracing.safe_query_summary(extracted, len(transcript)))
    return await _run_pipeline_for_extracted(extracted, trace_span, update_trace)


async def run_pipeline_for_confirmed(extracted: ExtractedQuery) -> QueryResponse:
    if tracing.is_over_daily_cap():
        return _service_unavailable_response()
    with tracing.trace_query(0) as (trace_span, update_trace, trace_id):
        update_trace(input=tracing.safe_query_summary(extracted, 0))
        # Gate 1 already passed for the original query this extraction came
        # from (a clarification only ever follows a passed Gate 1) — this is
        # the user confirming a suggested station, not new untrusted text, so
        # re-running Gate 1 here would be redundant, not a safety gap.
        try:
            response = await _run_pipeline_for_extracted(extracted, trace_span, update_trace)
        except UpstreamUnavailable:
            update_trace(output={"fallback_reason": FallbackReason.SERVICE_UNAVAILABLE})
            return _service_unavailable_response()
        response.trace_id = trace_id
        return response


async def _run_pipeline_for_extracted(
    extracted: ExtractedQuery, trace_span, update_trace
) -> QueryResponse:
    try:
        with tracing.stage_span("gate2-resolve") as span:
            stations = await gate2.resolve_stations(extracted, span=span)
    except ClarificationNeeded as exc:
        update_trace(output={"fallback_reason": exc.reason})
        return QueryResponse(
            text=exc.message,
            fallback_reason=exc.reason,
            clarification=ClarificationInfo(
                field=exc.field,
                suggested_station_name=exc.suggested_station_name,
                options=exc.options,
                extracted=ExtractedQueryFields(**extracted.model_dump()),
            ),
        )

    try:
        result = await next_service.find_next_service(stations, requested_time=extracted.time)
    except UnknownStation as exc:
        update_trace(output={"fallback_reason": FallbackReason.UNKNOWN_STATION})
        return QueryResponse(text=str(exc), fallback_reason=FallbackReason.UNKNOWN_STATION)

    if result.reason == "no_service_today":
        update_trace(output={"fallback_reason": FallbackReason.NO_SERVICE_TODAY})
        return QueryResponse(
            text=(
                f"There's no service running today between "
                f"{result.from_station.name} and {result.to_station.name}."
            ),
            fallback_reason=FallbackReason.NO_SERVICE_TODAY,
        )
    if result.reason == "no_route_found":
        update_trace(output={"fallback_reason": FallbackReason.NO_ROUTE_FOUND})
        return QueryResponse(
            text=(
                f"I can't find a direct or single-transfer route between "
                f"{result.from_station.name} and {result.to_station.name}. "
                f"Try the PTV journey planner: {_PTV_JOURNEY_PLANNER_URL}"
            ),
            fallback_reason=FallbackReason.NO_ROUTE_FOUND,
        )

    with tracing.stage_span("compose") as span:
        answer = await compose.compose_answer(result, span=span)

    # Cheapest lever when over the daily spend cap (addendum-02 Note B):
    # skip TTS, still return the text answer rather than failing the query.
    # A genuine TTS request failure degrades the same way — text-only is
    # still a usable answer, unlike STT/gate1 where there's nothing to
    # degrade to.
    audio = None
    if not tracing.is_over_daily_cap():
        try:
            with tracing.stage_span("tts") as span:
                audio = await tts.synthesize(answer, span=span)
        except UpstreamUnavailable:
            audio = None

    update_trace(output={"text": answer})
    return QueryResponse(text=answer, audio=audio)
