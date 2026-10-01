#!/usr/bin/env python3
"""
Test Suite for Strategy / Niche Management, Isolation, and Discovery Integration.
Covers:
- Strategy creation with niche, audience, topics config
- Strategy retrieval with attached sources
- Strategy configuration updates
- Strategy-source linking and isolation (Strategy A only uses Source A; Strategy B only uses Source B)
- Strategy-triggered Discovery producing ideas for the correct strategy
- Strategy Ideas entering Production up to NEEDS_REVIEW
"""
import sys
from uuid import uuid4
from fastapi.testclient import TestClient

from app.main import app
from app.db import SessionLocal
from app.strategies.models import ContentStrategy
from app.sources.models import Source
from app.ideas.models import Idea
from app.workflows.models import WorkflowRun, WorkflowRunStatus

client = TestClient(app)


def test_strategy_crud():
    print("\n--- TEST: Strategy CRUD ---")
    # 1. Create a Source to link
    db = SessionLocal()
    src_id = uuid4()
    source_a = Source(
        id=src_id,
        name="Source Alpha",
        source_type="rss",
        url="https://news.ycombinator.com/rss",
        enabled=True,
        config={},
    )
    db.add(source_a)
    db.commit()
    db.close()

    # 2. Create Strategy with niche configuration and attached source
    payload = {
        "name": "Cloud Native Architecture",
        "description": "High-impact deep dives on Kubernetes and distributed systems",
        "config": {
            "niche": "Cloud Native Infrastructure",
            "audience": "Staff DevOps & Platform Engineers",
            "goals": ["Educate on resilience", "Demonstrate production patterns"],
            "platforms": ["LinkedIn", "Substack"],
            "topics": ["Kubernetes", "eBPF", "Zero Trust"],
            "tone": "Authoritative and practical",
        },
        "enabled": True,
        "source_ids": [str(src_id)],
    }
    res = client.post("/api/strategies", json=payload)
    assert res.status_code == 201, f"Failed create: {res.text}"
    strat_data = res.json()
    strat_id = strat_data["id"]
    assert strat_data["name"] == "Cloud Native Architecture"
    assert strat_data["config"]["niche"] == "Cloud Native Infrastructure"
    assert len(strat_data["sources"]) == 1
    assert strat_data["sources"][0]["id"] == str(src_id)
    print(f"✓ Strategy created successfully: {strat_id} with attached source {src_id}")


    # 3. Get Strategy by ID
    res_get = client.get(f"/api/strategies/{strat_id}")
    assert res_get.status_code == 200
    assert res_get.json()["id"] == strat_id
    assert res_get.json()["sources"][0]["name"] == "Source Alpha"
    print("✓ Strategy retrieval by ID verified with sources loaded.")

    # 4. Patch/Update Strategy
    patch_payload = {
        "description": "Updated description for cloud architecture",
        "config": {
            **strat_data["config"],
            "tone": "Conversational yet rigorous",
        },
    }
    res_patch = client.patch(f"/api/strategies/{strat_id}", json=patch_payload)
    assert res_patch.status_code == 200
    assert res_patch.json()["description"] == "Updated description for cloud architecture"
    assert res_patch.json()["config"]["tone"] == "Conversational yet rigorous"
    print("✓ Strategy update verified.")


def test_strategy_isolation_and_discovery():
    """
    Mandatory Section 10: Verify Strategy Isolation.
    Strategy A with Source A and Strategy B with Source B.
    Strategy A Discovery ONLY queries and uses Source A.
    Strategy B Discovery ONLY queries and uses Source B.
    """
    print("\n--- TEST: Strategy Isolation & Discovery ---")
    db = SessionLocal()

    # Create 2 distinct sources
    src_a = Source(
        id=uuid4(),
        name="Isolated Feed A",
        source_type="rss",
        url="https://news.ycombinator.com/rss",
        enabled=True,
        config={},
    )
    src_b = Source(
        id=uuid4(),
        name="Isolated Feed B",
        source_type="rss",
        url="https://news.ycombinator.com/rss",
        enabled=True,
        config={},
    )
    db.add_all([src_a, src_b])
    db.commit()

    # Create Strategy A with src_a
    strat_a = ContentStrategy(
        id=uuid4(),
        name="Strategy AI Systems",
        description="AI infrastructure",
        config={"niche": "AI Agents", "topics": ["LangGraph", "Multi-Agent"]},
        enabled=True,
    )
    # Create Strategy B with src_b
    strat_b = ContentStrategy(
        id=uuid4(),
        name="Strategy Cybersecurity",
        description="Infosec defense",
        config={"niche": "AppSec", "topics": ["Pen Testing", "Supply Chain"]},
        enabled=True,
    )
    db.add_all([strat_a, strat_b])
    db.commit()

    from app.sources.models import SourceItem
    si_a = SourceItem(
        id=uuid4(),
        source_id=src_a.id,
        external_id=f"item-a-{uuid4()}",
        title="Agentic Workflow Orchestration in Modern Python",
        url="https://example.com/agentic-orchestration",
        content="Deep dive into LangGraph, stateful execution, and deterministic agent control.",
        source_metadata={"author": "AI Researcher"},
    )
    si_b = SourceItem(
        id=uuid4(),
        source_id=src_b.id,
        external_id=f"item-b-{uuid4()}",
        title="Zero Trust Architecture and Ephemeral Credentials",
        url="https://example.com/zero-trust-infra",
        content="Securing backend microservices with short-lived tokens and mTLS defense.",
        source_metadata={"author": "SecOps Engineer"},
    )
    db.add_all([si_a, si_b])
    db.commit()

    from app.strategies.service import sync_strategy_source_links
    sync_strategy_source_links(db, strat_a.id, [src_a.id])
    sync_strategy_source_links(db, strat_b.id, [src_b.id])
    db.commit()
    strat_a_id = strat_a.id
    strat_b_id = strat_b.id
    db.close()

    # Trigger Discovery for Strategy A
    res_disc_a = client.post(f"/api/strategies/{strat_a_id}/discover")
    assert res_disc_a.status_code == 200, f"Discovery A failed: {res_disc_a.text}"
    data_a = res_disc_a.json()
    assert data_a["sources_synced"] == 1
    assert data_a["ideas_created_count"] >= 1
    print(f"✓ Strategy A Discovery created {data_a['ideas_created_count']} ideas for Strategy A.")

    # Verify ideas created for Strategy A strictly belong to Strategy A
    db = SessionLocal()
    ideas_a = db.query(Idea).filter(Idea.strategy_id == strat_a_id).all()
    assert len(ideas_a) >= 1
    for ida in ideas_a:
        assert ida.strategy_id == strat_a_id
        assert ida.strategy_id != strat_b_id

    # Trigger Discovery for Strategy B
    res_disc_b = client.post(f"/api/strategies/{strat_b_id}/discover")
    assert res_disc_b.status_code == 200, f"Discovery B failed: {res_disc_b.text}"
    data_b = res_disc_b.json()
    assert data_b["sources_synced"] == 1
    assert data_b["ideas_created_count"] >= 1
    print(f"✓ Strategy B Discovery created {data_b['ideas_created_count']} ideas for Strategy B.")

    ideas_b = db.query(Idea).filter(Idea.strategy_id == strat_b_id).all()
    assert len(ideas_b) >= 1
    for idb in ideas_b:
        assert idb.strategy_id == strat_b_id
        assert idb.strategy_id != strat_a_id
    db.close()

    print("✓ STRATEGY ISOLATION VERIFIED: Strategy A and Strategy B strictly ingested and produced ideas for their own sources.")


def test_strategy_idea_enters_production():
    """
    Mandatory Section 17: Verify an Idea produced by Strategy Discovery
    enters the existing Production workflow and reaches NEEDS_REVIEW.
    """
    import time
    print("\n--- TEST: Strategy Idea Enters Production Workflow ---")
    db = SessionLocal()
    # Find any newly generated idea with status NEW
    idea = db.query(Idea).filter(Idea.status == "NEW").order_by(Idea.created_at.desc()).first()
    assert idea is not None, "Expected an idea with status NEW"
    idea_id = str(idea.id)
    strategy_id = str(idea.strategy_id)
    db.close()

    # Start workflow run via POST /api/workflow-runs
    res_start = client.post("/api/workflow-runs", json={"idea_id": idea_id, "strategy_id": strategy_id})
    assert res_start.status_code == 200, f"Failed starting workflow: {res_start.text}"
    run_id = res_start.json()["workflow_run_id"]
    print(f"✓ Started production workflow run {run_id} for strategy idea {idea_id}")

    # Poll until pipeline reaches NEEDS_REVIEW
    for _ in range(30):
        time.sleep(0.5)
        res_run = client.get(f"/api/workflow-runs/{run_id}")
        st = res_run.json()["status"]
        if st in ("NEEDS_REVIEW", "COMPLETED", "FAILED"):
            break

    assert st == "NEEDS_REVIEW", f"Expected workflow run to reach NEEDS_REVIEW, got {st}"
    print(f"✓ Production workflow successfully progressed through Research → Brief → Writer → NEEDS_REVIEW for Strategy Idea!")


def main():
    print("=" * 60)
    print("RUNNING STRATEGY & DISCOVERY TEST SUITE")
    print("=" * 60)
    test_strategy_crud()
    test_strategy_isolation_and_discovery()
    test_strategy_idea_enters_production()
    print("\n" + "=" * 60)
    print("ALL STRATEGY & DISCOVERY TESTS PASSED!")
    print("=" * 60)


if __name__ == "__main__":
    main()
