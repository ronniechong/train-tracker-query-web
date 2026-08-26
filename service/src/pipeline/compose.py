from datetime import datetime
from zoneinfo import ZoneInfo

from groq import AsyncGroq

from .next_service import NextServiceResult

_COMPOSITION_MODEL = "openai/gpt-oss-20b"
_MELBOURNE_TZ = ZoneInfo("Australia/Melbourne")

# Raised from 150 after real usage asked for full station names, platform,
# and am/pm on every time — that content alone runs ~185 chars for a
# two-leg journey. Cost impact is trivial (Orpheus TTS at $22/1M chars,
# still well under the $10/day cap addendum-02 priced against 150).
_CHARACTER_BUDGET = 220

_SYSTEM_PROMPT = (
    "You compose short answers for a Melbourne train schedule voice "
    "assistant, meant to be read aloud by text-to-speech. Use only the "
    "facts given — never invent times, stations, lines, or platforms. "
    "Write in full, natural spoken sentences a person would actually say "
    "out loud, connecting a two-leg journey with a word like \"then\". "
    "Every station must be named in full, e.g. \"Hoppers Crossing "
    "Station\", never just \"Hoppers Crossing\". Every departure time "
    "must include am or pm, e.g. \"3:35pm\", never a bare number like "
    "\"3:35\". Always state the platform for each leg, phrased as "
    "\"on Platform 1\". Only state an arrival time for the final "
    "destination of the whole journey (with am/pm) — not for an "
    "intermediate interchange. Example for a two-leg journey: \"Catch "
    "the 3:35pm from Hoppers Crossing Station on Platform 1 to Southern "
    "Cross Station. Then board the 4:10pm from Southern Cross Station on "
    "Platform 10 to Mooroolbark Station at 4:59pm.\" Never a list of "
    "clipped fragments. "
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
    return dt.strftime("%-I:%M%p").lower()


def _station_name(name: str) -> str:
    # "Hoppers Crossing Railway Station" -> "Hoppers Crossing Station" —
    # matches how people actually say these names out loud.
    return name.replace(" Railway Station", " Station")


def _facts(result: NextServiceResult) -> str:
    lines = []
    for i, leg in enumerate(result.legs, start=1):
        is_final_leg = i == len(result.legs)
        platform = f" on platform {leg.from_platform_code}" if leg.from_platform_code else ""
        arrival = (
            f", arriving {_local_time(leg.arrival_time)} at {_station_name(leg.to_station.name)}"
            if is_final_leg
            else ""
        )
        lines.append(
            f"Leg {i}: depart {_station_name(leg.from_station.name)} at "
            f"{_local_time(leg.departure_time)}{platform}, towards "
            f"{_station_name(leg.to_station.name)}{arrival}."
        )
    return "\n".join(lines)


def _fallback_answer(result: NextServiceResult) -> str:
    leg = result.legs[0]
    platform = f" on platform {leg.from_platform_code}" if leg.from_platform_code else ""
    answer = (
        f"Catch the {_local_time(leg.departure_time)} from "
        f"{_station_name(result.from_station.name)}{platform} to "
        f"{_station_name(result.to_station.name)}, arriving "
        f"{_local_time(leg.arrival_time)}."
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
