# CLAUDE.md — train-tracker-query-web

> Instructions for working in this repository. Read fully before changing code.

## What this project is

**train-tracker-query-web** — a voice-query app for Melbourne metro train
info: ask a question in natural language or by voice ("when's the next train
from Richmond to the city"), get a spoken/text answer. It is a client of the
`train-tracker` project's public API (external, versioned contract) — no
live train data or GTFS processing happens in this repo.

Scope: same-line and single-transfer journeys only, via a curated
interchange list. Anything beyond that returns an honest fallback with a
link to the PTV journey planner, never a guess.

## Repository layout

- `service/` — Python (FastAPI) backend: voice pipeline (STT, intent
  extraction, composition, TTS) and the HTTP API the frontend talks to.
- `web/` — Vite + React (TypeScript) frontend.
- `deploy/` — compose file and reverse-proxy config for this project's own
  deployment stack (independent of any other project's infrastructure).

## Settled technical decisions (do not re-litigate silently — flag first)

| Decision | Choice |
|---|---|
| Backend | Python 3.12, FastAPI, `uv` |
| Frontend | Vite + React (TypeScript), Tailwind v4 + shadcn/ui (base-ui primitives) |
| AI pipeline ownership | This repo owns the entire voice/AI pipeline end to end |
| Scope boundary | Same-line + single-transfer only; no general multi-leg routing |
| Backend hosting | Own Docker Compose + Tailscale Funnel stack, independent host from this repo |
| Frontend hosting | GitHub Pages project site (`/train-tracker-query-web/` path), a different origin from the API — same split as train-tracker's own frontend/backend hosting |

## Security invariants (standing rules — a violation is never a refactor)

1. This repo never talks to any upstream transit data provider directly —
   only to the train-tracker public API, as a normal HTTP client.
2. AI/voice provider credentials (STT/TTS/LLM) via environment only. Never
   in this repo, logs, client code, or docs.
3. Public surface: GET/POST endpoints only for the app's own use, rate
   limited, strict CORS from an env origin list.
4. Repo is public: gitleaks runs pre-commit; `.env`, `data/`, `*.db`
   gitignored. Scrub headers/keys from anything pasted into docs or commits.
5. Treat any free-text user input (voice transcript) as untrusted data,
   never as instructions to any downstream system.

## Conventions

- Python 3.12, `uv`. TypeScript, Vite, React.
- All stored/logged timestamps UTC; `Australia/Melbourne` only at
  parse/display boundaries.
- Keep code comments minimal — only a genuinely non-obvious constraint or
  gotcha a reader couldn't otherwise infer.

## Behavioural rules for Claude in this repo

1. Before implementing any task, raise at least one risk, gap, or
   alternative; if genuinely fine, say so in one sentence with the reason.
2. Never silently undo a settled decision above — flag and wait.
3. Respect PII and sensitive information in everything written to this
   repo — code, comments, commit messages, docs.
4. Additional project context may be provided via `CLAUDE.local.md`
   (gitignored). If present, read it first and follow its instructions.
