# train-tracker-query-web

A voice-query app for Melbourne metro train info. Ask a question in natural
language or by voice — "when's the next train from Richmond to the city" —
and get a spoken or text answer.

This is a client of [train-tracker](https://github.com/ronniechong/train-tracker)'s
public API. Scope: same-line and single-transfer journeys only.

## Layout

- `service/` — FastAPI backend (voice pipeline + HTTP API)
- `web/` — Vite + React frontend
- `deploy/` — deployment config

## Development

```
cd service && uv sync && uv run uvicorn src.main:app --reload
cd web && npm install && npm run dev
```

## Testing

`uv run pytest` runs the unit test suite (no external calls). The eval
suite (`tests/test_eval_harness.py`) hits live Groq and train-tracker
APIs to check extraction accuracy, station-matching robustness, and
answer-quality grading against curated fixtures in `eval/`. It's marked
`eval` and excluded by default — run it on demand:

```
cd service && uv run pytest -m eval -v
```

## License

MIT — see [LICENSE](LICENSE).
