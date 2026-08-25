import json
from enum import StrEnum

from groq import AsyncGroq

_INJECTION_GUARD_MODEL = "meta-llama/llama-prompt-guard-2-86m"
_RELEVANCE_MODEL = "openai/gpt-oss-20b"
_INJECTION_SCORE_THRESHOLD = 0.5

_RELEVANCE_SYSTEM_PROMPT = (
    "Classify the transcript as SCHEDULE_QUERY (asking when/how a specific "
    "train departs, arrives, or how to get from one station to another) or "
    "OFF_TOPIC (anything else, including general train-adjacent chat that "
    "is not a schedule/journey question). Respond only via the schema."
)

_RELEVANCE_SCHEMA = {
    "type": "object",
    "properties": {"label": {"type": "string", "enum": ["SCHEDULE_QUERY", "OFF_TOPIC"]}},
    "required": ["label"],
    "additionalProperties": False,
}

_client: AsyncGroq | None = None


def _get_client() -> AsyncGroq:
    global _client
    if _client is None:
        _client = AsyncGroq()
    return _client


class Gate1Outcome(StrEnum):
    PASS = "pass"
    INJECTION_BLOCKED = "injection_blocked"
    OFF_TOPIC = "off_topic"


async def check(transcript: str) -> Gate1Outcome:
    client = _get_client()

    guard = await client.chat.completions.create(
        model=_INJECTION_GUARD_MODEL,
        messages=[{"role": "user", "content": transcript}],
    )
    if float(guard.choices[0].message.content) > _INJECTION_SCORE_THRESHOLD:
        return Gate1Outcome.INJECTION_BLOCKED

    relevance = await client.chat.completions.create(
        model=_RELEVANCE_MODEL,
        temperature=0,
        messages=[
            {"role": "system", "content": _RELEVANCE_SYSTEM_PROMPT},
            {"role": "user", "content": transcript},
        ],
        response_format={
            "type": "json_schema",
            "json_schema": {"name": "relevance", "schema": _RELEVANCE_SCHEMA, "strict": True},
        },
    )
    label = json.loads(relevance.choices[0].message.content)["label"]
    if label == "OFF_TOPIC":
        return Gate1Outcome.OFF_TOPIC
    return Gate1Outcome.PASS
