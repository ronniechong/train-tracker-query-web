from enum import StrEnum

from pydantic import BaseModel


class FallbackReason(StrEnum):
    OFF_TOPIC = "off_topic"
    OUT_OF_SCOPE = "out_of_scope"
    AMBIGUOUS_STATION = "ambiguous_station"
    LOW_CONFIDENCE_STATION = "low_confidence_station"
    UNKNOWN_STATION = "unknown_station"
    NO_SERVICE_TODAY = "no_service_today"
    NO_ROUTE_FOUND = "no_route_found"


class ExtractedQueryFields(BaseModel):
    from_station: str | None
    to_station: str | None
    route_hint: str | None
    time: str | None


class ClarificationInfo(BaseModel):
    field: str  # "from" or "to" — which side needs disambiguation
    suggested_station_name: str | None
    extracted: ExtractedQueryFields  # the original query, to resubmit with a substitution


class QueryResponse(BaseModel):
    text: str
    audio: str | None = None
    fallback_reason: FallbackReason | None = None
    clarification: ClarificationInfo | None = None
