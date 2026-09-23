# Content Operating System — Development Guide

## Prerequisites

- Git
- Python 3.12
- Node.js
- npm
- Docker
- Docker Compose
- PostgreSQL

---

## Backend

```bash
cd backend
source ../.venv/bin/activate
```

Run FastAPI:

```bash
uvicorn app.main:app --reload
```

---

## Health Checks

```bash
curl http://localhost:8000/health
```

```bash
curl http://localhost:8000/health/db
```

Expected:

```json
{
	"status": "ok"
}
```

and:

```json
{
	"status": "ok",
	"db_result": 1
}
```

---

## Database

Development PostgreSQL runs locally.

Database configuration is provided through:

```text
DATABASE_URL
```

Secrets belong in `.env`.

Never commit `.env`.

`.env.example` documents required configuration.

---

## Migrations

Alembic manages database schema changes.

Migrations must be committed to Git.

Never manually modify an already-applied migration in a shared environment.

---

## Testing

Tests should be added alongside domain and workflow implementation.

Tests should cover:

* domain rules
* API behavior
* database constraints
* workflow transitions
* approval concurrency
* version locking
* publication idempotency

---

## Git

Use feature branches for significant changes.

Keep commits focused and descriptive.

Do not commit:

* `.env`
* secrets
* local database data
* virtual environments
* build artifacts
