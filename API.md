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

- `POST /api/workflow-runs` returns `status: PENDING` (queued). The scheduler worker starts the graph; `GET /api/workflow-runs/{id}` includes `worker_running` so the UI can say when nothing will start the run.
- `POST /api/workflow-runs/{id}/approval` queues the resume in the same transaction as the decision. The worker runs it.
- `POST /api/publications/{id}/analytics/sync`: Manually triggers metrics sync against the analytics provider (e.g. Buffer). Returns HTTP 201 on success with new snapshot, HTTP 409 if Buffer answered but has no metrics for the post yet (`not_ready`), HTTP 503 with `detail.state = "network_error"` if this server could not reach Buffer (DNS, timeout or connection failure; nothing is checked and no snapshot is written), or HTTP 404 if the post is not found. Every click's outcome is recorded on the publication and shown as "Last attempt".
- `GET /health/network`: Diagnostic run inside the backend process. For `api.buffer.com`, `openrouter.ai` and `github.com` it returns `{host, resolved, ip_count, http_status, error, ms}` per host plus `all_resolved`. Sends no credentials and never returns response bodies. Use it to tell "this server cannot resolve Buffer" apart from "Buffer has no metrics".
- `POST /api/publications/{id}/analytics/manual`: Submits verified metrics observed directly on LinkedIn (impressions, reactions, comments, clicks, shares). Stores an `analytics` record with `provider='manual'`, used as headline metrics if most recent.
- `GET /api/workflow-runs/{id}/publication`: Returns the publication record with `analytics_status` and `schedule_info`.
  - `analytics_status.state`: one of `available` (a valid Buffer snapshot exists), `manual` (latest valid snapshot was entered by hand), `not_collected_yet` (Buffer answered with no metrics), `network_error` (this server could not reach Buffer), `failed` (the last attempt failed with a provider error), `none` (no attempt and no valid snapshot). Exactly one state is shown; it comes from the most recent attempt, scheduled or manual.
  - `analytics_status.last_attempt_at`, `last_attempt_outcome`, `last_attempt_source` (`scheduler` or `manual`), `last_attempt_message`: the most recent attempt.
  - `analytics_status.last_buffer_response_at`: last time Buffer answered (`ready` or `not_ready`). Network failures never count.
  - `analytics_status.attempt_number`: rung on the metrics ladder (1 to 6). Network failures do not advance it.
  - `analytics_status.network_failures_in_row`, `network_retry_paused`: automatic retries after network failures wait 5 minutes and pause after 12 in a row. A successful sync resets the count.
  - `analytics_status.scheduler_running`: true when a worker heartbeat is fresher than 2 minutes. When false the UI says "Automatic sync is OFF. Start the worker: `python -m app.scheduler`."
  - `analytics_status.next_sync_at`, `next_sync_overdue`: a past scheduled time is flagged overdue, never shown as upcoming.
  - `analytics_status.valid_snapshot`: the newest snapshot that is not a stub and not quarantined.
  - `schedule_info.last_synced_at`: ISO timestamp of most recent successful sync.
  - `schedule_info.next_sync_at`: ISO timestamp of next scheduled sync attempt in backoff ladder.
  - `schedule_info.sync_attempt_count`: Attempts on the metrics ladder so far (network failures excluded).
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
