import os

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from .pipeline import tracing
from .pipeline.gate2 import ExtractedQuery
from .pipeline.models import QueryResponse
from .pipeline.orchestrator import run_pipeline, run_pipeline_for_confirmed, run_pipeline_for_transcript
from .pipeline.stations_cache import ScheduleUnavailable

load_dotenv()

MAX_AUDIO_BYTES = 5 * 1024 * 1024
MAX_TEXT_LENGTH = 500

# 10/minute per IP — generous enough that no real user notices it, tight
# enough to stop a runaway client from burning through Groq quota (this
# app has no auth, so per-IP is the only identity available).
_QUERY_RATE_LIMIT = "10/minute"


def _client_ip(request: Request) -> str:
    # In production this container only ever receives traffic from Caddy
    # on an internal-only network, which sets X-Real-IP to its own
    # trusted-proxy-resolved client address (see deploy/Caddyfile) — the
    # raw socket peer would otherwise be Caddy itself for every request,
    # collapsing rate limiting to one shared bucket for all users.
    return request.headers.get("X-Real-IP") or get_remote_address(request)


def _cors_origins() -> list[str]:
    raw = os.environ.get("CORS_ORIGINS", "")
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


limiter = Limiter(key_func=_client_ip)

app = FastAPI(title="train-tracker-query-web")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
# The frontend now lives on GitHub Pages, a different origin from this API
# (see deploy/Caddyfile) -- browser calls need this explicitly, an empty
# CORS_ORIGINS means no browser origin can call this API at all, not "allow
# everything".
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/query")
@limiter.limit(_QUERY_RATE_LIMIT)
async def query(request: Request) -> QueryResponse:
    chunks: list[bytes] = []
    total = 0
    async for chunk in request.stream():
        total += len(chunk)
        if total > MAX_AUDIO_BYTES:
            raise HTTPException(status_code=413, detail="Audio exceeds 5MB limit")
        chunks.append(chunk)
    audio_bytes = b"".join(chunks)

    try:
        return await run_pipeline(audio_bytes)
    except NotImplementedError as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc
    except ScheduleUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


class TextQuery(BaseModel):
    text: str


@app.post("/api/query/text")
@limiter.limit(_QUERY_RATE_LIMIT)
async def query_text(request: Request, body: TextQuery) -> QueryResponse:
    if len(body.text) > MAX_TEXT_LENGTH:
        raise HTTPException(status_code=413, detail=f"Text exceeds {MAX_TEXT_LENGTH} character limit")

    try:
        return await run_pipeline_for_transcript(body.text)
    except NotImplementedError as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc
    except ScheduleUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/api/query/confirm")
@limiter.limit(_QUERY_RATE_LIMIT)
async def query_confirm(request: Request, body: ExtractedQuery) -> QueryResponse:
    try:
        return await run_pipeline_for_confirmed(body)
    except NotImplementedError as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc
    except ScheduleUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


class FeedbackRequest(BaseModel):
    trace_id: str
    thumbs_up: bool


@app.post("/api/feedback")
def feedback(body: FeedbackRequest) -> dict[str, str]:
    tracing.record_feedback(body.trace_id, body.thumbs_up)
    return {"status": "ok"}
