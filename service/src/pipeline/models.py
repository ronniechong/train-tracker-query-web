from enum import StrEnum
from typing import Literal

from pydantic import BaseModel


class FallbackReason(StrEnum):
    OFF_TOPIC = "off_topic"
    OUT_OF_SCOPE = "out_of_scope"
    AMBIGUOUS_STATION = "ambiguous_station"
    LOW_CONFIDENCE_STATION = "low_confidence_station"
    UNKNOWN_STATION = "unknown_station"
    NO_SERVICE_TODAY = "no_service_today"
    NO_ROUTE_FOUND = "no_route_found"
    SERVICE_UNAVAILABLE = "service_unavailable"


class ExtractedQueryFields(BaseModel):
    from_station: str | None
    to_station: str | None
    route_hint: str | None
    time: str | None


class ClarificationInfo(BaseModel):
    field: str  # "from" or "to" — which side needs disambiguation
    suggested_station_name: str | None
    options: list[str] | None = None  # multiple real candidates (ambiguous match), pick one
    extracted: ExtractedQueryFields  # the original query, to resubmit with a substitution


class Highlight(BaseModel):
    # The exact substring to find in `text` — compose.py builds these with
    # the same deterministic formatting the composition prompt requires
    # the model to use verbatim (station names, times, platforms), so a
    # plain substring match against the composed sentence works. A
    # highlight that doesn't appear (the model phrased around it) is
    # simply not found — the frontend skips it silently, never an error.
    text: str
    kind: Literal["station", "platform", "time"]


class QueryResponse(BaseModel):
    text: str
    audio: str | None = None
    fallback_reason: FallbackReason | None = None
    clarification: ClarificationInfo | None = None
    highlights: list[Highlight] = []
    # The originating Langfuse trace, so the frontend can attach
    # thumbs-up/down feedback to the right trace. None when tracing isn't
    # configured (Langfuse keys unset) - feedback is then a no-op.
    trace_id: str | None = None
