# Content Operating System — Product Requirements Document

## 1. Product Overview

The Content Operating System is a workflow-driven platform that helps teams discover content opportunities, research selected topics, create structured content briefs and drafts, route content through human approval, publish approved content, and collect performance data.

The system is designed as an operating system for content production rather than a standalone AI writing tool.

The core lifecycle is:

Source Signals
→ Discovery
→ Opportunity Scoring
→ Human Selection
→ Research
→ Content Strategy
→ Writing
→ Human Approval
→ Publishing
→ Analytics

---

## 2. Problem Statement

Content production often involves disconnected activities:

- monitoring sources
- identifying trends
- deciding what is worth creating
- researching topics
- developing content strategy
- writing
- reviewing
- publishing
- measuring performance

These activities are frequently handled manually or through disconnected tools.

The Content Operating System aims to connect these stages into a persistent, traceable workflow.

---

## 3. Product Goal

Build a system that can:

1. Monitor configured information sources.
2. Normalize and deduplicate incoming source items.
3. Identify potential content opportunities.
4. Score opportunities against a configured content strategy.
5. Allow a human to select an idea.
6. Research the selected topic.
7. Generate a structured content brief.
8. Generate content from the approved research and brief.
9. Pause for human approval.
10. Support revision or rejection.
11. Publish approved content.
12. Collect publication analytics.
13. Preserve workflow history and provenance.

---

## 4. Core Principle

LLM for reasoning.

Code for control.

The system should use deterministic application logic for:

- persistence
- validation
- state transitions
- authorization
- deduplication
- concurrency control
- retries
- publishing
- analytics collection

LLMs should primarily be used where interpretation or generation is required.

---

## 5. Users

### Primary User

A content operator, creator, marketer, or content team member responsible for deciding what content should be created and approving generated content.

### User Responsibilities

The human remains responsible for:

- selecting content opportunities
- approving generated content
- requesting revisions
- rejecting content
- configuring content strategy
- configuring monitored sources

---

## 6. Core Concepts

### Content Strategy

Defines the goals, audience, topics, platforms, tone, and guidelines used to evaluate and produce content.

### Source

An external information source monitored by the system.

Examples:

- RSS feeds
- websites
- APIs
- YouTube
- Reddit
- search results

### Source Item

A specific piece of information collected from a source.

A Source Item is evidence/signaling data, not a content idea.

### Idea

A potential content opportunity derived from one or more source items.

An Idea represents an opportunity, not a production execution.

### Workflow Run

One attempt to turn an Idea into published content.

An Idea may have multiple Workflow Runs over its lifetime.

Only one active Workflow Run may exist for an Idea at a time.

### Research

Structured information gathered for a selected Idea.

### Content Brief

A structured plan describing what should be written and how it should be presented.

### Content

The logical content object.

### Content Version

An immutable version of the actual draft.

Edits and regenerations create new versions.

### Approval

A human decision associated with a specific Content Version.

### Publication

The result of publishing an approved Content Version to a platform.

### Analytics

Performance measurements associated with a Publication.

---

## 7. Discovery Workflow

Discovery is intentionally separate from production.

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
Scoring
    ↓
Ideas
    ↓
Human selects Idea
```

Discovery answers:

> What should we create?

---

## 8. Production Workflow

Production starts only after a human has selected an Idea.

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
    ├── REVISION → WRITER → APPROVAL
    └── REJECTED → END
```

Production answers:

> How do we turn this selected opportunity into content?

---

## 9. Functional Requirements

### FR-01 — Content Strategies

The system must allow users to create, view, update, enable, and disable content strategies.

A strategy should define:

* audience
* goals
* platforms
* content types
* topics
* tone
* voice guidelines

---

### FR-02 — Source Management

The system must allow users to configure sources.

A source must contain:

* name
* type
* URL or source identifier
* enabled state
* optional configuration metadata

---

### FR-03 — Source Synchronization

The system must be able to retrieve new source items from configured sources.

The system should avoid creating duplicate Source Items.

---

### FR-04 — Opportunity Discovery

The system must identify potential content opportunities from collected Source Items.

The system should preserve the relationship between Ideas and their supporting Source Items.

---

### FR-05 — Opportunity Scoring

Ideas should be evaluated using structured scoring dimensions:

* relevance
* trend
* novelty
* audience fit
* source quality

Initial scoring weights:

* relevance: 30%
* trend: 20%
* novelty: 15%
* audience fit: 20%
* source quality: 15%

The LLM may produce the individual dimensions, but application code calculates the final score.

---

### FR-06 — Human Idea Selection

A human must select an Idea before a production Workflow Run begins.

---

### FR-07 — Research

The system must research the selected Idea and produce structured research containing:

* summary
* key findings
* important claims
* supporting sources
* confidence

Research must preserve source provenance.

---

### FR-08 — Content Brief

The system must generate a structured brief containing information such as:

* angle
* hook
* target audience
* key points
* structure
* tone
* CTA
* platform
* content goal

---

### FR-09 — Content Generation

The Writer should generate content using:

* approved research
* content brief
* content strategy
* configured voice guidelines

The Writer should not freely browse external sources during normal content generation.

---

### FR-10 — Content Versioning

Generated or manually edited content must create a new Content Version.

Previous versions must remain immutable.

---

### FR-11 — Human Approval

The system must pause before publishing and require human approval.

Possible decisions:

* approve
* request revision
* reject

---

### FR-12 — Publishing

Approved Content Versions may be published to supported platforms.

Publishing must be idempotent to prevent duplicate publications caused by retries or network failures.

---

### FR-13 — Analytics

The system must collect performance measurements for publications.

Analytics should support multiple snapshots over time.

---

### FR-14 — Workflow Persistence

Workflow execution state must survive process restarts.

LangGraph checkpoints will be persisted using PostgreSQL.

---

## 10. Non-Functional Requirements

### Reliability

Transient infrastructure failures should be retryable.

Semantic/content-quality failures should not be blindly retried.

### Traceability

The system should be able to answer:

* where an Idea came from
* what research supported it
* which brief produced the content
* which version was approved
* where the content was published

### Concurrency Safety

The database must enforce critical invariants.

For example:

Only one active Workflow Run may exist for an Idea.

### Version Safety

Approval must reference the exact Content Version being reviewed.

A stale approval request must not approve a newer version accidentally.

### Security

Secrets must remain outside source control.

Environment variables should be used for credentials.

### Maintainability

External providers should be isolated behind integration interfaces.

---

## 11. V0 Scope

V0 includes:

* content strategies
* source configuration
* source items
* idea discovery
* idea scoring
* human idea selection
* research
* content briefs
* content generation
* content versioning
* human approval
* publishing abstraction
* analytics storage
* LangGraph orchestration
* PostgreSQL persistence

---

## 12. Explicitly Deferred

The following are intentionally deferred:

* semantic cross-run Idea deduplication
* advanced analytics intelligence
* automated performance-driven strategy optimization
* large-scale distributed workers
* microservices
* autonomous multi-agent collaboration
* complex scheduling infrastructure
* advanced recommendation systems

---

## 13. Success Criteria

A complete V0 should demonstrate this end-to-end path:

Source
→ Source Item
→ Idea
→ Human Selection
→ Workflow Run
→ Research
→ Content Brief
→ Draft
→ Human Approval
→ Publication
→ Analytics

The system must preserve the data and workflow history throughout this lifecycle.