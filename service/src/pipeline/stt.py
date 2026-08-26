from groq import AsyncGroq

_client: AsyncGroq | None = None

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


async def transcribe(audio_bytes: bytes) -> str:
    transcription = await _get_client().audio.transcriptions.create(
        model="whisper-large-v3-turbo",
        file=("audio.webm", audio_bytes, "audio/webm"),
        prompt=_STATION_NAME_PROMPT,
    )
    return transcription.text
