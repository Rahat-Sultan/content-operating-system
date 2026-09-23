---
inclusion: always
---

# Product: Content Operating System

## What this is

Not "an AI that writes content." A system that discovers opportunities,
researches them, plans content, drafts it, gets human approval, publishes,
measures results, and (eventually) learns from those results. The loop
feeding back into itself is the point — not a one-shot writer.

## The full conceptual loop

```
Content Strategy → Source Monitoring → Normalize/Dedupe → Scout →
Idea Scoring → [human selects idea] → Research → Content Brief →
Writer → Human Approval → Publish → Analytics → Learning → (back to Scoring)
```

## V0 scope — the only thing being built right now

One source. One platform. One niche. One content type. Full loop, small
scope. Two phases, not one:

**Discovery** (mostly deterministic + AI where needed):
`Source Sync → Normalize → Dedupe → Scout → Scoring → Idea`
Runs independently. Ideas exist without any production run attached to them.
Human browses `GET /ideas` and picks one.

**Production** (LangGraph-orchestrated):
`Research → Strategist → Writer → Human Approval → Publisher → Analytics`
Started explicitly via `POST /workflow-runs { strategy_id, idea_id }`.
Always requires an idea already selected — never starts undirected.

## Explicitly NOT in V0

Scheduling, multi-source, multi-platform, feedback/learning loop,
PerformanceInsight analysis, semantic idea dedup, multi-tenancy/workspaces,
image/asset generation. All real, all deliberately deferred — see
`architecture.md` for why (mainly: not enough data yet, or real effort with
no MVP payoff).

## Core principle

Design the complete system conceptually. Implement one vertical slice at a
time. If a request would build ahead of V0 scope, flag it before
implementing — don't silently expand scope because the code happens to be
adjacent.
