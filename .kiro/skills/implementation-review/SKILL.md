---
name: implementation-review
description: Use when implementing or modifying a significant feature in the Content Operating System. Inspect the existing architecture first, identify affected domain boundaries, implement incrementally, and verify the result.
---

# Implementation Review

Before changing code:

1. Inspect the existing implementation.
2. Identify the relevant domain and infrastructure boundaries.
3. Check existing patterns before introducing new abstractions.
4. Check the project's documentation and steering rules
   (`AGENTS.md`, `.kiro/steering/*.md`).
5. Explain the intended changes before making significant modifications.

During implementation:

- Keep changes focused.
- Do not rewrite unrelated working code.
- Do not introduce dependencies without justification.
- Preserve existing architectural boundaries (see `architecture.md`).
- Keep domain logic independent from FastAPI and LangGraph.
- Keep external provider code inside `tools/`.
- Use PostgreSQL constraints for important invariants — a check in
  application code is not a substitute for a database constraint.
- **Any state/status transition (approval, workflow start, publish,
  anything with an "active"/"in progress" concept) must be implemented as
  an atomic database operation — a conditional `UPDATE ... WHERE
  status = X` with a rowcount check, or a real unique constraint. Never a
  read-then-write check in application code.** This project has hit this
  exact bug twice already during design review (workflow concurrency,
  approval concurrency) — treat any new read-then-write state check as a
  bug, not a stylistic choice.
- Make side effects idempotent where appropriate (especially anything that
  calls an external API that might have partially succeeded).

After implementation:

1. Run relevant tests.
2. Run type/lint/build checks where applicable.
3. Verify database migrations if database changes were made — confirm
   `alembic upgrade head` runs clean.
4. Report files changed.
5. Report verification performed.
6. Identify any assumptions or remaining risks — explicitly call out if a
   new state transition was added and confirm it was made atomic.
