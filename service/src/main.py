from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request

from .pipeline.models import QueryResponse
from .pipeline.orchestrator import run_pipeline
from .pipeline.stations_cache import ScheduleUnavailable

load_dotenv()

MAX_AUDIO_BYTES = 5 * 1024 * 1024

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
