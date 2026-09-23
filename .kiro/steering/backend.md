---
inclusion: fileMatch
fileMatchPattern: "backend/**/*.py"
---

# Backend conventions

## Environment

- Python 3.12 via a project-local `.venv` (`python3.12 -m venv .venv`).
  Never use the system `python3` (currently 3.14) for this project, and
  never install packages with `sudo apt` — everything goes through `pip`
  inside the venv.
- Secrets live in `.env` (gitignored). `.env.example` is committed and kept
  in sync with every new required variable — no real values in it.
- Config is read once, through `app/config.py`'s `pydantic-settings`
  `Settings` object. No `os.environ` calls scattered through the codebase.

## Layering — do not skip a layer

```
FastAPI route → Application service → (LangGraph, for Production only) → PostgreSQL
```

- Routes: HTTP concerns only — validation, status codes, auth. No business
  logic in a route function.
- Services: business operations, transactions, calling LangGraph.
- LangGraph nodes: workflow-specific reasoning/orchestration, persisting
  artifacts through services/repositories — not raw SQL scattered in node
  files.
- Frontend never talks to PostgreSQL directly. Always through FastAPI.

## API shape

No internal node endpoints (`/run-scout`, `/run-writer`). Expose business
concepts: `/strategies`, `/sources`, `/ideas`, `/workflow-runs`,
`/workflow-runs/{id}/approval`, `/content`, `/publications`. Workflow starts
are asynchronous — `POST /workflow-runs` creates the run and returns
immediately; the client polls `GET /workflow-runs/{id}` (SSE/WebSockets can
come later, polling is fine for V0).

## LangGraph specifics

- Checkpointer is `PostgresSaver`, configured explicitly at graph
  compile time. **Never rely on the default in-memory checkpointer** — it
  does not survive a process restart, which breaks the entire
  pause-for-human-approval use case this project depends on.
- `RetryPolicy` goes on nodes that call external/flaky things (search
  APIs, fetch, publish). Do not attach retries to nodes whose failure is a
  quality/semantic problem (a bad draft isn't a retry, it's a REVISION
  branch).
- Interrupt nodes: keep them small, minimal side effects before the
  `interrupt()` call, since LangGraph re-runs the node from its start on
  resume.
- Every node reads/writes small IDs to graph state, not full objects — see
  `architecture.md`'s state table.

## Testing/verification checklist for any non-trivial change

1. Relevant tests pass.
2. Type/lint checks pass.
3. If a database change: migration exists and `alembic upgrade head` runs
   clean against a fresh database.
4. If a concurrency-sensitive path changed (approval, workflow start,
   publish): confirm the atomic constraint/transaction is still correct,
   not just "looks right" — this is the project's most repeated bug class.
