# Content Operating System — Database Design

## 1. Database

PostgreSQL is the primary relational database.

Development:

```text
Local PostgreSQL
```

Production:

```text
Supabase PostgreSQL
```

The application interacts with both through SQLAlchemy.

---

## 2. Core Tables

V0 tables:

1. content_strategies
2. sources
3. strategy_sources
4. source_items
5. ideas
6. idea_source_items
7. workflow_runs
8. research
9. content_briefs
10. content
11. content_versions
12. approvals
13. publications
14. analytics

---

## 3. Relationships

```text
ContentStrategy
	│
	├────────────── Source
	│                 │
	│                 └── SourceItem
	│                         │
	│                         └── Idea
	│
	└── Idea
		│
		└── WorkflowRun
			│
			├── Research
			├── ContentBrief
			└── Content
				│
				└── ContentVersion
					├── Approval
					└── Publication
						│
						└── Analytics
```

---

## 4. UUIDs

Domain entities use UUID primary keys.

---

## 5. Timestamps

Domain tables should generally contain:

* created_at
* updated_at

Event/history tables may additionally contain:

* resolved_at
* published_at
* collected_at

---

## 6. Source Deduplication

Source Items should avoid duplicate ingestion.

Where a stable external identifier exists, it should be used.

Fallback mechanisms may include:

* normalized URL
* content hash

---

## 7. Idea Provenance

Ideas may originate from multiple Source Items.

This relationship is represented by:

```text
idea_source_items
```

This allows the system to preserve why an Idea was created.

---

## 8. Workflow Run Concurrency

An Idea can have multiple Workflow Runs over its lifetime.

However:

> Only one non-terminal Workflow Run may be active for an Idea.

This must be enforced at the PostgreSQL level using a partial unique index.

---

## 9. Content Versioning

Content versions are immutable.

Each Content has multiple versions:

```text
Content
 ├── Version 1
 ├── Version 2
 └── Version 3
```

Constraint:

```text
UNIQUE(content_id, version_number)
```

---

## 10. Approval Version Lock

Approval must reference a specific Content Version.

An approval request must not approve whichever version happens to be current.

The API should reject stale approval requests with a conflict response.

---

## 11. Publishing Idempotency

Publication records should contain an idempotency key.

This prevents duplicate external publications when a platform accepts a request but the network fails before the application receives the response.

---

## 12. JSONB

JSONB is appropriate for flexible structures such as:

* strategy configuration
* source metadata
* research findings
* content brief structures
* publication metadata
* analytics metadata

JSONB should not replace normal relational columns where querying and constraints are important.

---

## 13. Deferred Database Concepts

Not included in V0:

* ResearchEvidence table
* PerformanceInsight table
* semantic Idea deduplication tables
* complex multi-tenant authorization model

These may be introduced when actual requirements justify them.
