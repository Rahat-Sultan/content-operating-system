# Content Operating System — Architecture Decisions

## ADR-001 — Modular Monolith

Decision:

Use a pragmatic modular monolith.

Reason:

The initial system does not have the operational complexity that justifies microservices.

---

## ADR-002 — PostgreSQL

Decision:

Use PostgreSQL as the application database.

Reason:

The system has relational domain data, workflow state, relationships, constraints, transactions, and JSONB requirements.

---

## ADR-003 — SQLAlchemy + Alembic

Decision:

Use SQLAlchemy 2 for persistence and Alembic for migrations.

Reason:

Provides explicit database modeling, transaction control, and versioned schema changes.

---

## ADR-004 — LangGraph

Decision:

Use LangGraph for durable workflow orchestration.

Reason:

The production workflow contains branching, human interruption, revision loops, persistence, and resumability.

---

## ADR-005 — Separate Discovery and Production

Decision:

Discovery and production are separate lifecycles.

Reason:

Discovery answers "what should we create?" while production answers "how do we execute this selected opportunity?"

This also keeps human selection before expensive production work.

---

## ADR-006 — WorkflowRun as Execution Identity

Decision:

Each production attempt gets its own WorkflowRun.

Reason:

One Idea can be attempted multiple times.

WorkflowRun.id may serve as LangGraph thread_id.

---

## ADR-007 — Human Approval

Decision:

Human approval is a first-class workflow boundary.

Reason:

Generated content should not automatically become published content.

---

## ADR-008 — Immutable Content Versions

Decision:

Content drafts are versioned rather than overwritten.

Reason:

Approval, revision, auditing, and publishing require knowing exactly which version was used.

---

## ADR-009 — Database-Enforced Workflow Concurrency

Decision:

Use a PostgreSQL partial unique index to enforce one active WorkflowRun per Idea.

Reason:

Application-level read-then-write checks are vulnerable to race conditions.

---

## ADR-010 — Approval Version Lock

Decision:

Approval requests must identify the exact Content Version being reviewed.

Reason:

Prevents stale UI requests from approving a different/newer version.

---

## ADR-011 — LLM for Reasoning, Code for Control

Decision:

LLMs perform interpretation and generation. Deterministic code controls persistence, validation, state transitions, concurrency, retries, and side effects.

Reason:

Improves reliability and debuggability.

---

## ADR-012 — No Vector Database in V0

Decision:

Do not introduce a separate vector database initially.

Reason:

The initial product does not require semantic retrieval at a scale that justifies another persistence system. PostgreSQL/pgvector can be introduced later if needed.

---

## ADR-013 — MCP Is Not Runtime Architecture

Decision:

MCP integrations are development/tooling concerns.

Reason:

The production application must remain independent of Kiro and MCP availability.

---

## ADR-014 — Provider Isolation

Decision:

External APIs are accessed through integration modules.

Reason:

Providers may change and business/domain code should not depend on provider-specific implementations.

---

## ADR-015 — OpenRouter as Primary LLM Gateway (NVIDIA NIM Regional Unavailability)

Decision:

Use OpenRouter (`https://openrouter.ai/api/v1/chat/completions`) as the primary external LLM gateway, leveraging free-tier models (primary: `nvidia/nemotron-3-super-120b-a12b:free`, fallback: `openrouter/free`), with explicit placeholder detection.

Reason:

NVIDIA NIM direct API (`build.nvidia.com`) is regionally restricted/blocked in this deployment location. OpenRouter provides reliable, unrestricted access to top open models (including NVIDIA Nemotron) without region locks, ensuring resilient structured discovery and scoring workflows.

---

## ADR-016 — Durable PostgreSQL-Backed Polling Scheduler for Discovery & Analytics

Decision:

Implement a dedicated worker process (`python -m app.scheduler`) polling PostgreSQL using an explicit jobs table (`scheduled_jobs`) with atomic claims via `SELECT ... FOR UPDATE SKIP LOCKED` (or conditional atomic updates with timeout-based claim expiry).

Reason:

Per AGENTS.md Rule 10 ("Don't add infrastructure because it's interesting") and Rule 11, we avoid introducing Redis, Celery, or new daemon services. In-process FastAPI background tasks do not survive server restarts, do not support cross-worker coordination, and cannot prevent duplicate runs when multiple backend workers run. APScheduler requires either an in-memory job store (lost on restart) or an external database plugin. A native PostgreSQL table with atomic row-level locks provides:
1. Complete restart durability across crashes.
2. Safe multi-worker concurrency with zero double-execution.
3. Automatic recovery of stale claimed jobs via heartbeat/lease timeouts.

Rejected alternatives:
- Redis + Celery: Rejected as unnecessary infrastructure overhead for V0.
- APScheduler: Rejected to avoid unnecessary framework dependencies when PostgreSQL transactional locks (`SKIP LOCKED`) cleanly solve the claim problem in plain Python.
- FastAPI BackgroundTasks: Rejected because background tasks are ephemeral and killed on uvicorn restart.

---

## ADR-017 — Analytics Feedback Loop Deferred

Decision:

Deliberately defer feeding analytics metrics directly back into idea discovery/scoring heuristics.

Reason:

Currently there are only a handful of published posts, which provides insufficient signal for statistical scoring, and metrics on recent posts are still stabilizing. This feedback loop will be revisited when there are roughly 20 or more published posts with settled performance metrics.

---

## ADR-018 — Analytics Validity Rule: Never Store Provider Placeholders as Real Data

Decision:

External provider analytics responses must only generate an `analytics` database snapshot if the provider explicitly certifies that post performance metrics have been collected (indicated by `metricsUpdatedAt > sentAt`). Responses where metrics have not yet been ingested return `MetricsNotAvailableError` (HTTP 409) or `MetricsUnsupportedError`, writing zero database rows.

Reason:

Buffer returns initial placeholder records immediately after publication where comments, reactions, and impressions are empty or zero, and `metricsUpdatedAt` reflects the publication dispatch timestamp. Treating uncollected placeholders as genuine performance data corrupted reporting by recording zero performance for posts that had real impressions on LinkedIn.

Measured behavior (2026-10-06, 7 real published posts, `python -m app.analytics.diagnose`):

- The earlier timestamp gate is wrong. Every response has `metricsUpdatedAt > sentAt`, including placeholders. Buffer's docs define `metricsUpdatedAt` as "the most recent ingestion, not the most recent network change", so it is not evidence of collected data.
- The shape is the signal. A placeholder reports only `Reactions` and `Comments` (both zero). A collected post also reports `Impressions`, `Reach` and `Eng. Rate`. Example: post `6ac3541…` (sent 5 Oct 07:39 UTC) reports Impressions 95, Reach 51, Reactions 2, Eng. Rate 2.11%.
- The gate is now: store only when the response reports a metric other than Reactions/Comments. A genuine zero with Impressions present is stored. Fixtures: `backend/tests/fixtures/buffer_post_collected_6ac3541.json`, `buffer_post_placeholder_6abf5652.json`.
- Buffer's developer docs say newly sent posts "can take up to ~24 hours before metrics first appear" with a daily refresh (https://developers.buffer.com/guides/post-metrics.md). Measured for `6ac3541…`: placeholder at about 12:28 UTC on 5 Oct (4.8 h after send), collected by 04:32 UTC on 6 Oct (21.0 h after send).
- Not explained: five older posts (sent 2 to 5 Oct, 24 h to 94 h old) still report only Reactions and Comments at zero, with one shared ingestion time. The docs say a missing metric "does not mean zero" and only lists metrics the network reported. Whether this is a delay beyond the documented window, a per-channel permission, or LinkedIn not reporting impressions for those posts is UNKNOWN. The channel is connected and carries `r_member_postAnalytics` and `r_member_profileAnalytics`. Settling question: does Buffer's own dashboard show impressions for those posts?

---

## ADR-019 — LinkedIn Plain-Text Rendering and Draft Immutability

Decision:

LinkedIn posts are converted from Markdown to clean plain text via `render_for_linkedin` strictly at the publishing dispatch boundary, saving the exact text in publication audit metadata. The stored `ContentVersion` body remains immutable and intact in Markdown.

Reason:

LinkedIn does not parse Markdown; raw `#` headers, `**bold**`, and `[link](url)` markup degrade post quality. The human reviewer verifies the Markdown draft and sees a 1:1 plain-text LinkedIn preview with character limit checks before approving. Preserving Markdown in `content_versions` maintains editorial formatting for potential multi-platform expansion.

---

## ADR-021 — Network Failures Are Their Own State

Decision:

A failure to reach the analytics provider (DNS, refused or reset connection, timeout) is reported as `network_error` ("Couldn't reach Buffer from this server"). It is never reported as "metrics not yet available", never stores a snapshot, and never consumes a rung of the metrics retry ladder. Retries run after 5 minutes and pause after 12 in a row.

Reason:

On 6 Oct 2026 the page showed a DNS failure and, at the same time, "Metrics Not Yet Available ... Attempt 1 of 6". The DNS failure had consumed the attempt. The two conditions need different fixes: a network fix versus waiting on Buffer.

---

## ADR-022 — Production Workflow Runs Execute in the Durable Scheduler Worker

Decision:

Starting a WorkflowRun and resuming one after approval are rows in `scheduled_jobs` (`job_type = WORKFLOW_RUN`), written in the same transaction as the state change. The worker (`python -m app.scheduler`) claims them and runs the graph. FastAPI `BackgroundTasks` is no longer used for workflows.

Reason:

A backend restart used to lose any run in progress. The queued job is in PostgreSQL, so it survives. Start claims `PENDING -> RUNNING` with a conditional UPDATE, so a duplicate job cannot run a graph twice. Long jobs renew their claim and heartbeat every 30 s, so a run longer than the 5-minute stale-claim timeout is not run a second time.

Trade-off:

Nothing runs a workflow unless the worker is running. The UI reports this (`worker_running`). Resume jobs are at-least-once: if the worker dies mid-resume, the job is retried from the LangGraph checkpoint. Publishing remains idempotent by key, so a retry cannot double-post.

Verified 2026-10-06 on a scratch copy of the database: start queued, worker started it to NEEDS_REVIEW, REJECTED approval queued, worker resumed it to REJECTED, zero publications created.

