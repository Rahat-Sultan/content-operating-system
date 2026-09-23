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

## 8. Publications

```http
GET /api/publications/{id}
GET /api/publications/{id}/analytics
```

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
