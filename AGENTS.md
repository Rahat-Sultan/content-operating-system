# AGENTS.md

Non-negotiable rules for any agent working on Content OS. Short on purpose —
detailed context lives in `.kiro/steering/`. If something here conflicts with
a steering file, this file wins.

1. **LLM for reasoning, code for control.** The LLM decides what's
   interesting, what's true, what angle to take, how to write it. Plain
   Python decides how to save it, how to publish it, how to score it against
   thresholds. Never let an LLM call a database or a publishing API directly.

2. **PostgreSQL is the source of truth. LangGraph state is temporary working
   context.** Don't put full objects (research reports, drafts) in graph
   state — put IDs, and load the record when a node needs it.

3. **Every state transition is an atomic database operation, never
   read-then-write.** Check-then-act in application code is a race
   condition. Use a conditional `UPDATE ... WHERE status = 'X'` and verify
   `rowcount == 1`, or a real unique constraint. This project has already
   been bitten by this pattern twice (workflow concurrency, approval
   concurrency) — do not reintroduce it anywhere else.

4. **Retry transient failures. Never retry semantic ones.** A search API
   timeout gets a `RetryPolicy`. A rejected draft gets a REVISION branch, not
   a retry.

5. **Interrupt nodes must be small and side-effect-light.** LangGraph
   re-executes a node from its beginning on resume. Never put an expensive
   call or a write immediately before an `interrupt()` in the same node.

6. **Content versions are immutable.** An edit creates a new version. Never
   update a `content_versions` row in place.

7. **Publishing must be idempotent.** Every publish attempt carries an
   idempotency key. Never fire a second publish request for the same
   content+platform without checking first.

8. **Discovery and Production are separate workflows.** Scout/Scoring
   happens in the Discovery phase and creates Ideas. `POST /workflow-runs`
   always requires an existing `idea_id` — it never starts with `idea_id =
   null`.

9. **Don't expose internal workflow nodes as API endpoints.** No
   `/run-scout`, `/run-writer`, etc. The frontend talks to business
   concepts (`/ideas`, `/workflow-runs`, `/approval`), never to LangGraph
   internals.

10. **Don't add infrastructure because it's interesting.** No new framework,
    MCP server, or abstraction without a concrete problem it solves for V0.
    Check `.kiro/steering/architecture.md` before introducing anything new.

11. **Build the vertical slice, not a layer at a time.** V0 is: one source,
    one platform, one niche, full loop from idea to published analytics.
    Don't build ahead of that scope without it being an explicit decision.

12. **Never assume a manual check matches what the running application
    actually uses.** Before trusting a manual `psql`, `curl`, or similar
    command's output, verify it's hitting the same host/port/socket the
    real service is configured to use (check `DATABASE_URL` in `.env`, the
    actual running process's flags via `ps aux`, etc.) — don't assume
    "localhost" or a default port is correct. This project has been bitten
    by silent alternate instances twice (a Unix-socket uvicorn process, and
    two simultaneously-running PostgreSQL clusters both named
    `contentos_dev`) — both times, a manual check against the wrong
    instance caused a false alarm that looked like data loss or a broken
    connection.
