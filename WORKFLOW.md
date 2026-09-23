# Content Operating System — Workflow Design

## 1. Two Distinct Lifecycles

The system intentionally separates Discovery from Production.

---

## 2. Discovery

```text
Strategy
 ↓
Source Sync
 ↓
Source Items
 ↓
Normalize / Deduplicate
 ↓
Scout
 ↓
Score
 ↓
Ideas
 ↓
Human Selection
```

Discovery asks:

> What should we create?

Discovery does not automatically start production.

---

## 3. Production

Production begins after the human selects an Idea.

```text
START
 ↓
RESEARCH
 ↓
STRATEGIST
 ↓
WRITER
 ↓
APPROVAL
```

Approval branches:

```text
APPROVED
	↓
PUBLISHER
	↓
ANALYTICS
	↓
END
```

```text
REVISION REQUESTED
	↓
WRITER
	↓
APPROVAL
```

```text
REJECTED
	↓
END
```

---

## 4. Workflow Identity

Each production execution has a WorkflowRun.

WorkflowRun.id may be used as the LangGraph thread_id.

An Idea must not be used as the thread_id because an Idea may have multiple production attempts.

---

## 5. LangGraph State

The graph state should remain small.

Expected fields:

* workflow_run_id
* strategy_id
* idea_id
* research_id
* content_brief_id
* content_id
* current_content_version_id
* approval_status
* approval_feedback
* publication_id
* error

Large documents and domain records belong in PostgreSQL, not graph state.

---

## 6. Human Approval

Approval is an interrupt boundary.

Approval nodes should be:

* small
* side-effect-light
* safe to re-execute

The approval API must atomically update the WorkflowRun state.

---

## 7. Failure Handling

Retry transient infrastructure failures:

* API timeout
* rate limiting
* temporary provider failure
* network failure

Do not blindly retry:

* human rejection
* content-quality problems
* invalid user input

---

## 8. Side Effects

Before retrying or resuming any node, ask:

> What happens if this node executes twice?

Non-idempotent side effects require protection.

Publishing requires idempotency.

---

## 9. Workflow Errors

Durable workflow failures must be stored in:

```text
workflow_runs.error
workflow_runs.status
```

Graph state may contain the working error context, but PostgreSQL remains the durable source of truth.
