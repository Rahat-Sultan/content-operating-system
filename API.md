# Content Operating System — API Design

## 1. API

Backend API:

```text
FastAPI
```

Frontend communicates with the backend through HTTP.

---

## 2. Principles

* APIs represent business operations.
* Frontend does not know LangGraph implementation details.
* Frontend never accesses PostgreSQL directly.
* Workflow state transitions are validated server-side.
* APIs return durable domain state.

---

## 3. Strategies

```http
POST /api/strategies
GET /api/strategies
GET /api/strategies/{id}
PATCH /api/strategies/{id}
POST /api/strategies/{id}/discover
```

---

## 4. Sources

```http
POST /api/sources
GET /api/sources
GET /api/sources/{id}
PATCH /api/sources/{id}
POST /api/sources/{id}/sync
```

---

## 5. Ideas

```http
GET /api/ideas
GET /api/ideas/{id}
```

---

## 6. Workflow Runs

Start production:

```http
POST /api/workflow-runs
```

Request:

```json
{
	"strategy_id": "...",
	"idea_id": "..."
}
```

Other operations:

```http
GET /api/workflow-runs
GET /api/workflow-runs/{id}
POST /api/workflow-runs/{id}/cancel
POST /api/workflow-runs/{id}/approval
```

---

## 7. Content

```http
GET /api/content/{id}
GET /api/content/{id}/versions
GET /api/content-versions/{id}
POST /api/content/{id}/versions
```

Manual edits create new versions.

---

## 8. Publications & Analytics

```http
GET /api/publications/{id}
GET /api/publications/{id}/analytics
POST /api/publications/{id}/analytics/sync
POST /api/publications/{id}/analytics/manual
GET /api/workflow-runs/{id}/publication
GET /api/workflow-runs/{id}/draft
```

- `POST /api/publications/{id}/analytics/sync`: Manually triggers metrics sync against the analytics provider (e.g. Buffer). Returns HTTP 201 on success with new snapshot, HTTP 409 if metrics are not yet available (provider collection delay), or HTTP 404 if the post is not found.
- `POST /api/publications/{id}/analytics/manual`: Submits verified metrics observed directly on LinkedIn (impressions, reactions, comments, clicks, shares). Stores an `analytics` record with `provider='manual'`, used as headline metrics if most recent.
- `GET /api/workflow-runs/{id}/publication`: Returns the publication record with `schedule_info`:
  - `last_synced_at`: ISO timestamp of most recent successful sync.
  - `next_sync_at`: ISO timestamp of next scheduled sync attempt in backoff ladder.
  - `sync_attempt_count`: Total sync attempts executed so far.
- `GET /api/workflow-runs/{id}/draft`: Returns draft versions and summary, including `linkedin_preview` (clean plain-text rendered string for LinkedIn), `char_count`, and `will_truncate` boolean flag.
- `GET /api/strategies/{id}`: Returns strategy with `schedule_info`:
  - `interval_hours`: Configured discovery interval in hours.
  - `is_scheduled`: Boolean indicating if automatic background discovery is active.
  - `last_run`: Status, timestamp, items found, and ideas created during the last scheduled run.

---

## 9. Approval

Approval requests must include:

* content_version_id
* decision
* feedback

The server must verify that the submitted version is the version currently awaiting review.

Stale requests return:

```text
409 Conflict
```

---

## 10. Workflow Start Concurrency

Starting a Workflow Run must be safe against concurrent requests.

The database enforces one active Workflow Run per Idea.

A conflicting request should return an appropriate conflict response rather than creating two active runs.

---

## 11. Authentication

Authentication and authorization are API-boundary concerns.

The initial V0 authorization model may remain simple unless multi-user requirements are introduced.
