---
inclusion: fileMatch
fileMatchPattern: "backend/app/graph/**/*.py"
---

# Workflow (LangGraph) rules

## Production graph topology (V0)

```
START → RESEARCH → STRATEGIST → WRITER → APPROVAL
                                            │
                        ┌───────────────────┼───────────────────┐
                     REJECT              REVISION              APPROVE
                        │                   │                     │
                       END                WRITER              PUBLISHER
                                             │                     │
                                          APPROVAL              ANALYTICS
                                                                    │
                                                                   END
```

Discovery (Scout, Scoring) is NOT in this graph — it's a separate
deterministic application service that runs before a WorkflowRun ever
starts. See `product.md`.

## ContentGraphState — keep it small

```python
class ContentGraphState(TypedDict):
    workflow_run_id: UUID
    strategy_id: UUID
    idea_id: UUID                  # required at start, never null

    research_id: UUID | None
    content_brief_id: UUID | None
    content_id: UUID | None
    current_content_version_id: UUID | None

    approval_status: str | None
    approval_feedback: str | None

    publication_id: UUID | None
    error: str | None
```

No full Research/Brief/Draft objects in state — IDs only. A node that needs
the full record loads it from Postgres by ID.

## Node responsibilities — not every node is an LLM call

| Node | LLM? |
|---|---|
| Research | Yes — search/fetch tools + reasoning |
| Strategist | Yes |
| Writer | Yes |
| Approval | No — human interrupt, no LLM |
| Publisher | No — normal API code |
| Analytics collector | No — normal API code |

The Writer never searches the web itself. It receives the ContentBrief +
approved Research and writes from that only — this prevents unsupported
claims, topic drift, and hallucinated citations. If the Writer needs new
information, that's a sign Research was incomplete, not a reason to give
Writer search tools.

## Error handling

On a non-retryable failure, route to a terminal node that persists the
failure reason to `workflow_runs.status = 'FAILED'` and
`workflow_runs.error`, not just to the transient `state.error` field — the
graph checkpoint isn't queryable by the API; the database row is.

## Idempotent publishing

Publisher node must check `publications.idempotency_key` before firing a
publish request. On ambiguous failure (e.g. network timeout after the
platform may have already accepted the post), do not blindly retry —
reconcile via the stored idempotency key / external post ID first.
