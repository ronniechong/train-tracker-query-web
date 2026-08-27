import base64

from groq import AsyncGroq, GroqError

from . import tracing
from .errors import UpstreamUnavailable

_TTS_MODEL = "canopylabs/orpheus-v1-english"
_VOICE = "autumn"

# Only wav is supported for this model — mp3/other formats are rejected
# by the API.
_RESPONSE_FORMAT = "wav"

_client: AsyncGroq | None = None


def _get_client() -> AsyncGroq:
    global _client
    if _client is None:
        _client = AsyncGroq()
    return _client


async def synthesize(text: str, span=None) -> str:
    try:
        response = await _get_client().audio.speech.create(
            input=text,
            model=_TTS_MODEL,
            voice=_VOICE,
            response_format=_RESPONSE_FORMAT,
        )
        audio_bytes = await response.read()
    except GroqError as exc:
        raise UpstreamUnavailable("TTS request failed") from exc
    tracing.record_cost(span, _TTS_MODEL, tracing.tts_cost_usd(len(text)))
    return base64.b64encode(audio_bytes).decode("ascii")
