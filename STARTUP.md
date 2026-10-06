# Content OS — Startup Guide & Environment Manual

Project root: `~/BxTrackSolution/content-os` (`/home/borat/BxTrackSolution/content-os`)

Run through this procedure every time after a reboot or fresh terminal session.

---

## 1. Required Environment

- **OS**: Linux (WSL / Ubuntu)
- **Python**: Python 3.12 (`/home/borat/BxTrackSolution/content-os/.venv`)
- **Node.js**: v22+ (`node -v` -> v22.23.2)
- **PostgreSQL**: PostgreSQL 18 binaries at `/usr/lib/postgresql/18/bin/`

---

## 2. PostgreSQL Architecture & Isolation

⚠️ **IMPORTANT ARCHITECTURAL RULE:**
There have historically been two PostgreSQL 18 clusters on this system:
1. **Redundant system cluster**: `/var/lib/postgresql/18/main` (managed by system service, empty database).
2. **Project-local cluster (REAL)**: `/home/borat/BxTrackSolution/content-os/.pgdata` with Unix domain socket directory `/home/borat/BxTrackSolution/content-os/.pgsockets`.

The Content OS application and LangGraph checkpoints run **strictly and exclusively** on the project-local cluster:
- **Data directory**: `~/BxTrackSolution/content-os/.pgdata`
- **Unix socket directory**: `~/BxTrackSolution/content-os/.pgsockets`
- **Database name**: `contentos_dev`
- **Port**: 5432 (bound to Unix socket)

Connecting to the wrong instance leads to false reports of data loss or missing tables. The redundant system cluster should remain stopped and not used.

---

## 3. Verified PostgreSQL Startup Command

Check if the project-local PostgreSQL process is already running:
```bash
ps -ef | grep "postgres -D.*content-os/.pgdata"
```

If it is not running, start it using the verified direct postgres daemon command:
```bash
/usr/lib/postgresql/18/bin/postgres \
  -D /home/borat/BxTrackSolution/content-os/.pgdata \
  -k /home/borat/BxTrackSolution/content-os/.pgsockets \
  -h "" \
  -p 5432
```
*(Run in a dedicated background task or terminal window).*

### PostgreSQL Readiness Verification
Verify that the project-local cluster is accepting connections on its dedicated socket:
```bash
/usr/lib/postgresql/18/bin/pg_isready -h /home/borat/BxTrackSolution/content-os/.pgsockets -p 5432
```
Expected output:
```
/home/borat/BxTrackSolution/content-os/.pgsockets:5432 - accepting connections
```

---

## 4. Manual Database Connection & Identity Verification

Always connect directly to the project socket to guarantee targeting the real application database:
```bash
psql -h /home/borat/BxTrackSolution/content-os/.pgsockets -U contentos -d contentos_dev
```

### Optional PGHOST shortcut:
Add to `~/.bashrc`:
```bash
export PGHOST=/home/borat/BxTrackSolution/content-os/.pgsockets
```
After `source ~/.bashrc`, a bare `psql -U contentos -d contentos_dev` will default to the project-local socket.

### Database Identity Verification Query
Run this query to inspect database identity and verify server directory:
```sql
SELECT current_database(), current_user, inet_server_addr(), inet_server_port();
SHOW data_directory;
SELECT count(*) FROM ideas;
SELECT count(*) FROM workflow_runs;
```
Expected:
- `current_database`: `contentos_dev`
- `data_directory`: `/home/borat/BxTrackSolution/content-os/.pgdata`
- `ideas` count: >= 6

---

## 5. Backend Startup (FastAPI)

Open a dedicated terminal:
```bash
cd ~/BxTrackSolution/content-os/backend
source ../.venv/bin/activate
python --version   # Must be 3.12.x
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

⚠️ Always use standard HTTP on port 8000 (`http://localhost:8000`). Never run with `--uds`.

### Backend Health Verification
```bash
curl http://localhost:8000/health
curl http://localhost:8000/api/ideas
```
Expected: `{"status":"ok"}` and a JSON array of ideas.

---

## 6. Frontend Startup (Next.js)

Open a dedicated terminal:
```bash
cd ~/BxTrackSolution/content-os/frontend
npm run dev -- -p 3000
```
Open `http://localhost:3000` in the browser. Always port 3000.

### Frontend/Backend Connectivity Verification
- Open `http://localhost:3000/ideas` in your browser.
- Verify ideas load and render with scores.
- Check browser devtools console: no CORS errors, no failed API calls.

### Refresh vs. Sync Metrics Semantics
- **Refresh Button (Top Right)**: Re-reads local application data from the local database for the workflow run, idea, research, brief, publication, and existing analytics snapshots. Invalidates client-side React Query cache and displays an explicit green "Updated HH:MM:SS" badge on completion.
- **Sync Metrics Button (Publication Card)**: Calls the external analytics provider API (e.g. Buffer GraphQL) to fetch live metrics. If metrics are still uncollected by Buffer, returns HTTP 409 and shows Amber "Metrics Not Yet Available". Automatically re-fetches local snapshots when new data arrives.

---

## 7. Scheduler Startup & Testing (Background Worker)

The background worker automatically polls PostgreSQL for due scheduled discoveries and analytics sync jobs.
Each loop it writes a heartbeat row to `worker_heartbeats`; the publication page reads it to show whether automatic sync is running.

### Scheduler Startup
Start the backend and the scheduler from **your own terminal**, not from an agent sandbox. A sandbox without DNS makes every Buffer call fail. Run the migration once after pulling:
```bash
cd ~/BxTrackSolution/content-os/backend
source ../.venv/bin/activate
alembic upgrade head        # adds worker_heartbeats (revision a4c7e2b91f30)
python -m app.scheduler
```

### Production workflows need the worker
Starting a workflow (`POST /api/workflow-runs`) and approving it both queue a job; the worker runs the graph. Without `python -m app.scheduler` running, a new run stays **PENDING** and the run page says "Queued. Nothing is running it." Runs survive a backend restart because the queued job is in PostgreSQL.

### Re-running the Buffer diagnostic
Read-only. Sends only `post(input: {id})` queries for real published posts, prints a table, never writes to the database, never prints the token:
```bash
cd ~/BxTrackSolution/content-os/backend
../.venv/bin/python -m app.analytics.diagnose                    # table
../.venv/bin/python -m app.analytics.diagnose --save-raw DIR     # also write redacted raw JSON per post
```
Local-test publications (`linkedin_*`, `test-ext-*`, `stub_*`) are skipped: they are not Buffer posts.

### Network check
With the backend running: `curl http://localhost:8000/health/network`. All three hosts should show `resolved: true`.

Environment variables:
- `SCHEDULER_POLL_INTERVAL`: Polling interval in seconds (default `2.0`).
- `MIN_DISCOVERY_INTERVAL_HOURS`: Minimum allowed discovery interval for strategies (default `1.0`, overridable to `0.0` for testing).

### Running Scheduler Tests
```bash
cd ~/BxTrackSolution/content-os/backend
PYTHONPATH=. ../.venv/bin/python tests/test_schedule_calculator.py
PYTHONPATH=. ../.venv/bin/python tests/test_scheduled_discovery_auto.py
PYTHONPATH=. ../.venv/bin/python tests/test_scheduled_discovery_concurrency.py
PYTHONPATH=. ../.venv/bin/python tests/test_scheduled_analytics_sync.py
```

---

## 8. Clean Shutdown Procedure

1. **Frontend**: Stop Next.js process (`Ctrl+C` in the frontend terminal).
2. **Backend**: Stop uvicorn process (`Ctrl+C` in the backend terminal).
3. **Scheduler**: Stop scheduler worker (`Ctrl+C` in the scheduler terminal).
4. **PostgreSQL**: Stop local postgres cleanly:
   ```bash
   /usr/lib/postgresql/18/bin/pg_ctl -D /home/borat/BxTrackSolution/content-os/.pgdata stop
   ```
   Or send `SIGTERM` to the root postgres daemon PID recorded in `.pgdata/postmaster.pid`.

---

## 9. Troubleshooting Guide

### Issue: "Database appears empty" or "table does not exist"
- **Cause**: You connected via TCP `localhost:5432` or default socket to the empty system PostgreSQL instance.
- **Fix**: Check `DATABASE_URL` in `backend/.env`. Always specify `-h /home/borat/BxTrackSolution/content-os/.pgsockets` when running `psql`.

### Issue: PostgreSQL socket missing
- **Cause**: Directory `.pgsockets` does not exist or stale socket files are blocking creation.
- **Fix**: Run `mkdir -p /home/borat/BxTrackSolution/content-os/.pgsockets` and remove stale `.s.PGSQL.*` files before launching.

### Issue: Backend cannot connect (`could not connect to server`)
- **Cause**: Local PostgreSQL is not running or socket path mismatch.
- **Fix**: Check `/usr/lib/postgresql/18/bin/pg_isready -h /home/borat/BxTrackSolution/content-os/.pgsockets` and verify `DATABASE_URL` in `backend/.env`.

### Issue: Address already in use (`Errno 98` / `EADDRINUSE`) on port 8000 or 3000
- **Cause**: Previous uvicorn or Next.js instance is still running in background.
- **Fix**:
  ```bash
  fuser -k 8000/tcp
  fuser -k 3000/tcp
  ```

### Issue: Frontend cannot reach backend
- **Cause**: Backend is down or `NEXT_PUBLIC_API_URL` is pointed to the wrong URL.
- **Fix**: Ensure `curl http://localhost:8000/health` returns `{"status":"ok"}` and frontend uses `http://localhost:8000/api`.

---

## 9. Non-Negotiable Safety Rule

> **Never assume a manual database verification command targets the same instance used by the application.** Before trusting manual verification, inspect `backend/.env`'s `DATABASE_URL` and explicitly verify the target host, port, or Unix socket against the running PostgreSQL process.
