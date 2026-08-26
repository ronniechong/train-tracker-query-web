from . import compose, declines, gate1, gate2, next_service, stt, tts
from .gate1 import Gate1Outcome
from .gate2 import ClarificationNeeded, ExtractedQuery
from .models import ClarificationInfo, ExtractedQueryFields, FallbackReason, QueryResponse
from .next_service import UnknownStation

_PTV_JOURNEY_PLANNER_URL = "https://www.ptv.vic.gov.au/journey"


async def run_pipeline(audio_bytes: bytes) -> QueryResponse:
    transcript = await stt.transcribe(audio_bytes)
    return await run_pipeline_for_transcript(transcript)


async def run_pipeline_for_transcript(transcript: str) -> QueryResponse:
    gate1_outcome = await gate1.check(transcript)
    if gate1_outcome is not Gate1Outcome.PASS:
        return QueryResponse(
            text=declines.random_decline(),
            fallback_reason=FallbackReason.OFF_TOPIC,
        )

    extracted = await gate2.extract(transcript)
    return await _run_pipeline_for_extracted(extracted)


async def run_pipeline_for_confirmed(extracted: ExtractedQuery) -> QueryResponse:
    # Gate 1 already passed for the original query this extraction came
    # from (a clarification only ever follows a passed Gate 1) — this is
    # the user confirming a suggested station, not new untrusted text, so
    # re-running Gate 1 here would be redundant, not a safety gap.
    return await _run_pipeline_for_extracted(extracted)


async def _run_pipeline_for_extracted(extracted: ExtractedQuery) -> QueryResponse:
    try:
        stations = await gate2.resolve_stations(extracted)
    except ClarificationNeeded as exc:
        return QueryResponse(
            text=exc.message,
            fallback_reason=exc.reason,
            clarification=ClarificationInfo(
                field=exc.field,
                suggested_station_name=exc.suggested_station_name,
                extracted=ExtractedQueryFields(**extracted.model_dump()),
            ),
        )

    try:
        result = await next_service.find_next_service(stations, requested_time=extracted.time)
    except UnknownStation as exc:
        return QueryResponse(text=str(exc), fallback_reason=FallbackReason.UNKNOWN_STATION)

    if result.reason == "no_service_today":
        return QueryResponse(
            text=(
                f"There's no service running today between "
                f"{result.from_station.name} and {result.to_station.name}."
            ),
            fallback_reason=FallbackReason.NO_SERVICE_TODAY,
        )
    if result.reason == "no_route_found":
        return QueryResponse(
            text=(
                f"I can't find a direct or single-transfer route between "
                f"{result.from_station.name} and {result.to_station.name}. "
                f"Try the PTV journey planner: {_PTV_JOURNEY_PLANNER_URL}"
            ),
            fallback_reason=FallbackReason.NO_ROUTE_FOUND,
        )

    answer = await compose.compose_answer(result)
    audio = await tts.synthesize(answer)
    return QueryResponse(text=answer, audio=audio)
