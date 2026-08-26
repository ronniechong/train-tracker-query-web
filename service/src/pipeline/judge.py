import json

from groq import AsyncGroq
from pydantic import BaseModel

from . import tracing

_JUDGE_MODEL = "openai/gpt-oss-20b"

# The judge is never shown the original spoken transcript - only the
# expected outcome and the assistant's actual response - matching the
# same fields-only scoping the eval sets and Langfuse tracing use (see
# CLAUDE.md's transcript-retention decision). Grading against a
# transcript the judge was never meant to see would silently reintroduce
# the thing that decision explicitly avoided.
_JUDGE_SYSTEM_PROMPT = (
    "You grade a Melbourne train-schedule voice assistant's answer "
    "against an expected outcome. You are never shown the original "
    "spoken query - only the expected outcome category, expected "
    "extracted fields (from/to/route/time - the query's intent, not the "
    "schedule), and the assistant's actual response text. Grade three "
    "things independently: (1) accuracy - does the response match the "
    "expected outcome category (success/clarification/fallback)? For a "
    "success response, does it name the expected stations (allowing for "
    "the full official name, e.g. 'Richmond' matching 'Richmond Railway "
    "Station')? A success response legitimately includes real schedule "
    "details - departure/arrival times, platforms, headsigns - that "
    "come from a live timetable lookup and are NOT expected to appear in "
    "expected_fields; only flag accuracy as failing if the response "
    "contradicts the expected fields (wrong stations) or the wrong "
    "outcome category, never merely for including schedule specifics "
    "beyond what was extracted from the query. If expected_fields.time is "
    "set, it is a 'next train AT OR AFTER this time' filter, not an "
    "expected exact departure time - a response with any departure time "
    "at or after it is correct; only flag it if the departure is before "
    "the requested time. (2) tone - is it a "
    "natural, spoken-friendly sentence suitable for text-to-speech, not "
    "a raw error dump or a list of clipped fragments; (3) length - is it "
    "reasonably concise, not padded or rambling. Respond only via the "
    "schema."
)

_JUDGE_SCHEMA = {
    "type": "object",
    "properties": {
        "accuracy_pass": {"type": "boolean"},
        "tone_pass": {"type": "boolean"},
        "length_pass": {"type": "boolean"},
        "notes": {"type": "string"},
    },
    "required": ["accuracy_pass", "tone_pass", "length_pass", "notes"],
    "additionalProperties": False,
}

_client: AsyncGroq | None = None


def _get_client() -> AsyncGroq:
    global _client
    if _client is None:
        _client = AsyncGroq()
    return _client


class JudgeVerdict(BaseModel):
    accuracy_pass: bool
    tone_pass: bool
    length_pass: bool
    notes: str

    @property
    def overall_pass(self) -> bool:
        return self.accuracy_pass and self.tone_pass and self.length_pass


async def grade(
    expected_category: str,
    expected_fields: dict | None,
    answer_text: str,
    span=None,
) -> JudgeVerdict:
    user_content = json.dumps(
        {
            "expected_category": expected_category,
            "expected_fields": expected_fields,
            "actual_answer": answer_text,
        }
    )
    response = await _get_client().chat.completions.create(
        model=_JUDGE_MODEL,
        temperature=0,
        messages=[
            {"role": "system", "content": _JUDGE_SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        response_format={
            "type": "json_schema",
            "json_schema": {"name": "judge_verdict", "schema": _JUDGE_SCHEMA, "strict": True},
        },
    )
    tracing.record_chat_cost(span, _JUDGE_MODEL, response)
    return JudgeVerdict.model_validate_json(response.choices[0].message.content)
