# Content Operating System

A workflow-driven content operating system that discovers content opportunities, researches selected topics, generates structured content, routes drafts through human approval, publishes approved content, and collects performance analytics.

## Architecture

```text
Sources
	↓
Discovery
	↓
Ideas
	↓
Human Selection
	↓
Research
	↓
Content Brief
	↓
Writer
	↓
Human Approval
	↓
Publishing
	↓
Analytics
```

## Stack

### Frontend

* Next.js
* React
* TypeScript
* Tailwind CSS

### Backend

* Python
* FastAPI
* SQLAlchemy
* Alembic
* LangGraph

### Data

* PostgreSQL
* LangGraph PostgreSQL checkpointing

### AI

* OpenRouter

## Development

See `DEVELOPMENT.md`.

## Documentation

* `PRD.md` — product requirements
* `ARCHITECTURE.md` — system architecture
* `DATABASE.md` — database design
* `API.md` — API design
* `WORKFLOW.md` — workflow design
* `DECISIONS.md` — architectural decisions
* `ROADMAP.md` — implementation roadmap
