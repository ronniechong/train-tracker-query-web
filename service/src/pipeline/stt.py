from groq import AsyncGroq, GroqError

from . import tracing
from .errors import UpstreamUnavailable

_client: AsyncGroq | None = None
_MODEL = "whisper-large-v3-turbo"

# Whisper's prompt biases transcription toward listed vocabulary, but
# only actually helps up to a point — a full ~900-character list of
# station names (the API's hard limit) measured identically to no prompt
# at all in live testing ("Mooroolbark" mistranscribed the same way
# either way). A much shorter, curated list of genuinely hard/uncommon
# station names measurably helped ("Mooroolbark" → "Morrowbark" instead
# of "Moral Bark" — not perfect, but close enough for Gate 2's fuzzy
# match to still resolve it). Deliberately not comprehensive: covers
# known-hard names by manual judgment, not every station.
_STATION_NAME_PROMPT = (
    "Melbourne train stations: Mooroolbark, Nunawading, Wantirna, Upper "
    "Ferntree Gully, Ferntree Gully, Belgrave, Croydon, Heathmont, "
    "Bayswater, Mitcham, Elsternwick, Balaclava, Toorak, Kooyong, "
    "Heyington, Hawksburn, Glenferrie, Riversdale, Willison, Alamein, "
    "Ashburton, Gardiner, Glen Iris."
)


def _get_client() -> AsyncGroq:
    global _client
    if _client is None:
        _client = AsyncGroq()
    return _client


async def transcribe(audio_bytes: bytes, span=None) -> str:
    try:
        transcription = await _get_client().audio.transcriptions.create(
            model=_MODEL,
            file=("audio.webm", audio_bytes, "audio/webm"),
            prompt=_STATION_NAME_PROMPT,
        )
    except GroqError as exc:
        raise UpstreamUnavailable("STT request failed") from exc
    tracing.record_cost(span, _MODEL, tracing.stt_cost_usd())
    return transcription.text
