---
inclusion: always
---

# Architecture

## The stack, and why

```
Next.js  →  FastAPI  →  Application Services  →  LangGraph  →  PostgreSQL
                                                       ↕
                                                   OpenRouter (LLM gateway)
```

- **FastAPI is the HTTP boundary only.** Not the workflow. Routes call
  services; services call LangGraph or plain business logic.
- **LangGraph orchestrates the Production workflow only** (Research →
  Publish). Discovery is a deterministic application service, not a graph —
  it doesn't need pause/resume/branching the way Production does.
- **CrewAI was evaluated and rejected** in favor of LangGraph, specifically
  because this system is fundamentally a stateful workflow with branching,
  persistence, and human-in-the-loop — not a "team of autonomous agents
  collaborating" problem. Do not introduce CrewAI, LangChain-the-framework,
  or a second orchestration layer alongside LangGraph. One orchestrator.
- **OpenRouter is the only LLM gateway.** Don't call OpenAI/Anthropic/Google
  SDKs directly — go through OpenRouter so models are swappable per agent
  without rewriting call sites. Free-tier `:free` models are acceptable for
  V0 development; expect them to be weaker at structured JSON output than
  paid models, so validate outputs.
- **MCP is a tool-access boundary, not the whole architecture.** Use it for
  external services (Supabase admin, third-party APIs). Don't wrap an
  internal Python function in MCP just because MCP exists. Supabase MCP is a
  dev/admin tool only — the running application always talks to Postgres
  through SQLAlchemy, never through MCP.

## Backend folder structure (hybrid: domain modules + orchestration layer)

```
backend/app/
├── graph/            # LangGraph topology only — state, nodes, edges
│   ├── state.py
│   ├── content_graph.py
│   └── nodes/
├── strategies/ sources/ ideas/ workflows/ content/ publishing/ analytics/
│                      # business/domain modules — models, services, routes
├── tools/             # search, fetch, youtube, reddit, publisher clients
└── main.py
```

Domain logic lives in the feature modules. LangGraph is a separate
orchestration layer that calls into domain services — it does not contain
business logic itself.

## Three kinds of state — do not conflate them

| Kind | Owner | Example |
|---|---|---|
| Workflow state | LangGraph + PostgresSaver checkpointer | `current_node`, `status = PAUSED` |
| Application data | PostgreSQL (our own tables) | the actual Idea, Research, Draft rows |
| LLM context | Whatever's assembled for one reasoning call | strategy + idea + research + brand guide |

Graph state should carry **IDs and small working data**, not full database
objects. A node that needs the full Research record loads it by
`research_id` — it doesn't carry it through state forever.

## Idea vs. WorkflowRun

An `Idea` is a business opportunity. A `WorkflowRun` is one attempt to turn
it into published content. One idea can have multiple runs (e.g. a failed
run gets a fresh run, not a fresh idea). Only one *active* WorkflowRun is
allowed per idea at a time — enforced at the database level (see
`database.md`), not just in application code.

## What we deliberately are NOT building yet, and why

- `ResearchEvidence`, `PerformanceInsight` tables — not enough published
  history yet for either to mean anything.
- Feedback/learning loop — same reason; would add noise before signal.
- `DiscoveryRun`/`AgentRun`/`NodeRun` execution-history hierarchy —
  overengineering for V0; add only if Discovery itself needs
  scheduling/retries/history later.
- Multi-tenancy/Workspace model — don't design into a corner, but don't
  build it until a real multi-user requirement exists.
- Asset/image generation — text-first for V0; add when a visual platform is
  actually prioritized.

Do not implement any of the above without it being an explicit, discussed
decision — these were deferred on purpose, not forgotten.
