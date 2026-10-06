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

---

## ADR-019 — LinkedIn Plain-Text Rendering and Draft Immutability

Decision:

LinkedIn posts are converted from Markdown to clean plain text via `render_for_linkedin` strictly at the publishing dispatch boundary, saving the exact text in publication audit metadata. The stored `ContentVersion` body remains immutable and intact in Markdown.

Reason:

LinkedIn does not parse Markdown; raw `#` headers, `**bold**`, and `[link](url)` markup degrade post quality. The human reviewer verifies the Markdown draft and sees a 1:1 plain-text LinkedIn preview with character limit checks before approving. Preserving Markdown in `content_versions` maintains editorial formatting for potential multi-platform expansion.
