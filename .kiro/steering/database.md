---
inclusion: fileMatch
fileMatchPattern: "**/*.py"
---

# Database invariants

PostgreSQL owns all application data. LangGraph's `PostgresSaver` owns
workflow checkpoints in its own tables. Never mix these schemas
conceptually or query LangGraph's internal checkpoint tables directly from
application code.

## ID strategy

UUID primary keys everywhere. `workflow_runs.id` IS the LangGraph
`thread_id` — do not maintain a separate `thread_id` column that's supposed
to always equal `id`; pass `workflow_runs.id` directly as the thread
identifier.

## V0 tables (do not add more without discussion)

```
content_strategies, sources, strategy_sources, source_items, ideas,
idea_source_items, workflow_runs, research, content_briefs, content,
content_versions, approvals, publications, analytics
```

## Constraints that MUST exist — these are not optional hardening,
## they are the fix for concurrency bugs already found during design

- **`workflow_runs`**: partial unique index —
  `UNIQUE(idea_id) WHERE status IN ('PENDING','RUNNING','PAUSED','NEEDS_REVIEW','PUBLISHING')`
  — prevents two active production runs on the same idea.
- **`source_items`**: `UNIQUE(source_id, external_id)` where `external_id`
  is present; fall back to a `content_hash` uniqueness check when it isn't.
  Without this, concurrent syncs can insert duplicates.
- **`publications`**: `UNIQUE(idempotency_key)` (or
  `UNIQUE(content_version_id, platform)`). The `idempotency_key` column
  existing is not enough — it must be constrained, or a retried publish can
  post twice.
- **`content_versions`**: `UNIQUE(content_id, version_number)`. Versions are
  immutable — an edit inserts a new row, never updates an existing one.
  Include an `origin` field (`writer_agent` / `human_edit`) so the UI can
  distinguish AI drafts from human edits.

## Approval flow — must be one transaction, atomic check first

```
BEGIN
  UPDATE workflow_runs SET status = 'RUNNING'
  WHERE id = :id AND status = 'NEEDS_REVIEW'
  -- if rowcount != 1: ROLLBACK, return 409 Conflict, do not touch approvals
  INSERT INTO approvals (...)
  -- resume LangGraph only after both succeed
COMMIT
```

The approval request must also carry `content_version_id` and the backend
must verify it matches the version currently under review — reject with 409
if a human edit created a newer version while the request was in flight
(the "two tabs" problem).

## ideas.status values (must be explicit, not left open)

`NEW / SELECTED / IN_PROGRESS / PUBLISHED / REJECTED / EXPIRED` — decide
what a rejected idea's fate is (selectable again vs. permanently retired)
before implementing the Discovery dashboard, since the `workflow_runs`
partial unique index depends on idea state being unambiguous.

## Scoring

`ideas` stores five individual scores (`relevance_score`, `trend_score`,
`novelty_score`, `audience_fit_score`, `source_quality_score`) plus
`final_score`. All five come from **one** structured LLM call — never five
separate calls. Python computes the weighted `final_score`; the LLM never
computes the final number itself.

## Migrations

SQLAlchemy 2 + Alembic. Every constraint above goes in the initial
migration, not added later as an afterthought.
