from fastapi import FastAPI

app = FastAPI(title="train-tracker-query-web")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
