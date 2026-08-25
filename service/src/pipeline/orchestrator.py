from . import compose, gate1, gate2, next_service, stt, tts
from .models import QueryResponse


def run_pipeline(audio_bytes: bytes) -> QueryResponse:
    transcript = stt.transcribe(audio_bytes)

    if not gate1.is_in_scope(transcript):
        return QueryResponse(
            text="I can only help with Melbourne metro train times.",
            fallback_reason="out_of_scope",
        )

    extracted = gate2.extract(transcript)
    stations = gate2.resolve_stations(extracted)
    result = next_service.find_next_service(stations, extracted.route_hint)
    answer = compose.compose_answer(result)
    audio = tts.synthesize(answer)
    return QueryResponse(text=answer, audio=audio)
