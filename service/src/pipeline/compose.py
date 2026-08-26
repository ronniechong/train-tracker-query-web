from datetime import datetime
from zoneinfo import ZoneInfo

from groq import AsyncGroq

from .next_service import NextServiceResult

_COMPOSITION_MODEL = "openai/gpt-oss-20b"
_MELBOURNE_TZ = ZoneInfo("Australia/Melbourne")

# Matches the 150-char cap the $10/day cost ceiling was priced against
# (Milestone 02 decision gate) — Orpheus TTS bills per character.
_CHARACTER_BUDGET = 150

_SYSTEM_PROMPT = (
    "You compose short answers for a Melbourne train schedule voice "
    "assistant, meant to be read aloud by text-to-speech. Use only the "
    "facts given — never invent times, stations, lines, or platforms. "
    "Write in full, natural spoken sentences a person would actually say "
    "out loud, like \"Catch the 6:18pm from Croydon, platform 1 — it "
    "gets you to Flinders Street by 7:04.\" Never a list of clipped "
    "fragments like \"6:18 PM, Croydon platform 1 to Flinders Street.\" "
    "For a two-leg journey, connect the legs with a word like \"then\" "
    "or \"from there\". Mention platforms only if they fit naturally. "
    f"Stay under {_CHARACTER_BUDGET} characters."
)

_client: AsyncGroq | None = None


def _get_client() -> AsyncGroq:
    global _client
    if _client is None:
        _client = AsyncGroq()
    return _client


def _local_time(iso_timestamp: str) -> str:
    dt = datetime.fromisoformat(iso_timestamp).astimezone(_MELBOURNE_TZ)
    return dt.strftime("%-I:%M %p")


def _facts(result: NextServiceResult) -> str:
    lines = []
    for i, leg in enumerate(result.legs, start=1):
        platform = f", platform {leg.from_platform_code}" if leg.from_platform_code else ""
        lines.append(
            f"Leg {i}: depart {leg.from_station.name} at {_local_time(leg.departure_time)}"
            f"{platform}, arrive {leg.to_station.name} at {_local_time(leg.arrival_time)}, "
            f"towards {leg.headsign}."
        )
    return "\n".join(lines)


def _fallback_answer(result: NextServiceResult) -> str:
    leg = result.legs[0]
    platform = f", platform {leg.from_platform_code}" if leg.from_platform_code else ""
    answer = (
        f"Next train from {result.from_station.name} to {result.to_station.name} "
        f"departs at {_local_time(leg.departure_time)}{platform}."
    )
    return answer[:_CHARACTER_BUDGET]


async def compose_answer(result: NextServiceResult) -> str:
    response = await _get_client().chat.completions.create(
        model=_COMPOSITION_MODEL,
        temperature=0.3,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": _facts(result)},
        ],
    )
    answer = (response.choices[0].message.content or "").strip()
    if not answer or len(answer) > _CHARACTER_BUDGET:
        return _fallback_answer(result)
    return answer
