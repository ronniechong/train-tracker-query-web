from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel

from .pipeline import tracing
from .pipeline.gate2 import ExtractedQuery
from .pipeline.models import QueryResponse
from .pipeline.orchestrator import run_pipeline, run_pipeline_for_confirmed, run_pipeline_for_transcript
from .pipeline.stations_cache import ScheduleUnavailable

load_dotenv()

MAX_AUDIO_BYTES = 5 * 1024 * 1024
MAX_TEXT_LENGTH = 500

app = FastAPI(title="train-tracker-query-web")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/query")
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
async def query_text(body: TextQuery) -> QueryResponse:
    if len(body.text) > MAX_TEXT_LENGTH:
        raise HTTPException(status_code=413, detail=f"Text exceeds {MAX_TEXT_LENGTH} character limit")

    try:
        return await run_pipeline_for_transcript(body.text)
    except NotImplementedError as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc
    except ScheduleUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/api/query/confirm")
async def query_confirm(body: ExtractedQuery) -> QueryResponse:
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
