from groq import AsyncGroq

_client: AsyncGroq | None = None


def _get_client() -> AsyncGroq:
    global _client
    if _client is None:
        _client = AsyncGroq()
    return _client


async def transcribe(audio_bytes: bytes) -> str:
    transcription = await _get_client().audio.transcriptions.create(
        model="whisper-large-v3-turbo",
        file=("audio.webm", audio_bytes, "audio/webm"),
    )
    return transcription.text
