# Content Operating System — Architecture

## 1. Architecture Style

The system uses a pragmatic modular monolith.

It is intentionally not designed as microservices.

The backend is organized around domain modules while LangGraph remains a separate orchestration layer.

---

## 2. High-Level Architecture

```text
Next.js / React
	│
	│ HTTP
	▼
FastAPI
	│
	▼
Application Services
	│
   ┌───┴───────────────┐
   │                   │
Domain              Workflows
Logic               LangGraph
   │                   │
   └───────┬───────────┘
	    ▼
     Infrastructure
     ┌─────┼──────┐
     │     │      │
 PostgreSQL LLM  External APIs
```

---

## 3. Frontend

Technology:

* Next.js
* React
* TypeScript
* Tailwind CSS
* shadcn/ui where appropriate

The frontend communicates with FastAPI through HTTP APIs.

The frontend must not directly access PostgreSQL.

The frontend should not know LangGraph node names or internal graph implementation details.

---

## 4. Backend

Technology:

* Python
* FastAPI
* SQLAlchemy 2
* Alembic
* PostgreSQL

FastAPI is the HTTP boundary.

It is not the workflow engine.

---

## 5. Domain Modules

Core modules:

```text
strategies
sources
ideas
workflows
content
publishing
analytics
```

Domain logic should not depend directly on FastAPI, HTTP, or concrete external providers.

---

## 6. Workflow Layer

LangGraph is responsible for orchestrating production workflows.

Production graph:

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
 ├── APPROVED → PUBLISHER → ANALYTICS → END
 ├── REVISION → WRITER
 └── REJECTED → END
```

Discovery is separate from this graph.

---

## 7. PostgreSQL Responsibilities

PostgreSQL has two conceptual responsibilities.

### Application Data

Stores:

* strategies
* sources
* source items
* ideas
* workflow runs
* research
* briefs
* content
* versions
* approvals
* publications
* analytics

### Workflow Checkpoints

LangGraph PostgreSQL checkpoint storage records workflow execution state.

These are logically separate responsibilities.

Application schema should not be designed around LangGraph checkpoint tables.

---

## 8. State Ownership

### PostgreSQL

Source of truth for business/domain data.

### LangGraph State

Working memory required to execute the current workflow.

### LangGraph Checkpointer

Durable workflow execution state.

Principle:

> PostgreSQL knows what the system knows. LangGraph knows where the workflow is.

---

## 9. LLM Boundary

OpenRouter is used as the LLM gateway.

The application should isolate LLM calls behind an integration layer.

LLMs should handle:

* interpretation
* classification
* scoring
* research synthesis
* strategy generation
* writing

Application code should handle:

* validation
* persistence
* state transitions
* concurrency
* retries
* publishing
* analytics

---

## 10. External Integrations

External services should be isolated behind integration modules.

Examples:

```text
integrations/
├── llm/
├── search/
├── sources/
└── platforms/
```

This prevents provider-specific code from spreading throughout the application.

---

## 11. MCP

MCP is a development/tool integration mechanism.

It is not part of the application's core runtime architecture.

MCP may be used by Kiro for:

* GitHub operations
* Supabase administration
* browser inspection
* documentation/tool access

The production application should not depend on Kiro being available.

---

## 12. Design Principles

1. LLM for reasoning, code for control.
2. PostgreSQL is the application source of truth.
3. Human approval is a first-class workflow state.
4. External providers are isolated.
5. Domain logic should remain independent of LangGraph.
6. Avoid premature microservices.
7. Prefer durable state over ephemeral agent context.
8. Make side effects idempotent.
9. Preserve provenance.
10. Keep graph state small.
