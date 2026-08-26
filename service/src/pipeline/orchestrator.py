from . import compose, declines, gate1, gate2, next_service, stt, tts
from .gate1 import Gate1Outcome
from .gate2 import ClarificationNeeded
from .models import FallbackReason, QueryResponse


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
    try:
        stations = await gate2.resolve_stations(extracted)
    except ClarificationNeeded as exc:
        return QueryResponse(text=exc.message, fallback_reason=exc.reason)

    result = next_service.find_next_service(stations, extracted.route_hint)
    answer = compose.compose_answer(result)
    audio = tts.synthesize(answer)
    return QueryResponse(text=answer, audio=audio)
