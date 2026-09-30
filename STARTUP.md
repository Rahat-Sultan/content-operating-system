# Content OS — Startup Checklist

Run through this every time after a reboot or a fresh terminal session, in order.
Each step includes the check to confirm it actually worked before moving to the next.

## 1. PostgreSQL

Check if it's already running (it may auto-start on boot — confirm rather than assume):
```bash
sudo systemctl status postgresql@18-main --no-pager
```
Look for `Active: active (running)`. If it's not running:
```bash
sudo systemctl start postgresql@18-main
```

**Confirm the app can actually connect** (not just that the service is "active" — this uses
the real app credentials, same check used throughout this project):
```bash
PGPASSWORD=devpassword psql -h localhost -U contentos -d contentos_dev -c "SELECT current_user, current_database();"
```
Expect a row back showing `contentos | contentos_dev`.

## 2. Backend (FastAPI)

Open a **dedicated terminal window** for this — it needs to keep running the whole session,
don't reuse this terminal for other commands.

```bash
cd ~/BxTrackSolution/content-os/backend
source ../.venv/bin/activate
uvicorn app.main:app --reload
```

Confirm the venv activated correctly before trusting uvicorn:
```bash
python --version   # should print 3.12.14, not the system default 3.14
```
(Run this *before* the `uvicorn` command above, as a quick sanity check.)

**In a second terminal**, confirm the backend is actually reachable:
```bash
curl http://localhost:8000/health
curl http://localhost:8000/api/ideas
```
Expect `{"status":"ok"}` and a real JSON list.

⚠️ Do not start uvicorn with `--uds` (Unix socket) — this project has hit connection
failures from that before. Always plain `uvicorn app.main:app --reload`, which defaults
to `http://127.0.0.1:8000`, matching what the frontend expects.

## 3. Frontend (Next.js)

Another **dedicated terminal window**, separate from the backend one:
```bash
cd ~/BxTrackSolution/content-os/frontend
npm run dev
```
Open `http://localhost:3000` in a browser once it says `Ready`.

## 4. Sanity checks before doing real work

- `git status` — check nothing unexpected is sitting modified/untracked from a previous
  session before starting new changes.
- If using Kiro: confirm the `postgres` and `github` MCP servers show as connected in its
  MCP panel (Docker Desktop must be running first if using the GitHub MCP server —
  `docker ps` should return cleanly, not a "cannot connect to daemon" error).
- If a port is already in use (`Address already in use` on 8000 or 3000), something from a
  prior session is still running:
  ```bash
  lsof -i :8000   # or :3000
  kill <pid>
  ```

## Quick reference — the three things that must all be true before the app works

| Check | Command | Expect |
|---|---|---|
| Postgres up | `sudo systemctl status postgresql@18-main --no-pager` | `active (running)` |
| Backend reachable | `curl http://localhost:8000/health` | `{"status":"ok"}` |
| Frontend reachable | open `http://localhost:3000` | page loads, no build error |

If any of these three fail, fix that one before assuming the others are the problem —
this project has repeatedly found that a downstream error (like a frontend build failure)
often traces back to one of these three not actually being up.
