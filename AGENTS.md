# AGENTS.md

Cross-tool agent instructions for this repo. See `CLAUDE.md` for full
project context, architecture, and behavioural rules — this file is the
short form for tools that read `AGENTS.md` instead.

## Commands

```
# backend
cd service && uv sync && uv run uvicorn src.main:app --reload
cd service && uv run pytest

# frontend
cd web && npm install && npm run dev
cd web && npm run build
```

## Commit style

Conventional Commits (`feat`, `fix`, `chore`, `docs`, `build`, etc.), e.g.
`fix(service): handle empty station query`. No AI co-author trailers.

## Rules

Read `CLAUDE.md` before making changes — settled decisions, security
invariants, and repo layout live there. Do not undo a settled decision
silently.
