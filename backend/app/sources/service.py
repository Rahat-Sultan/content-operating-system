import logging
from typing import Any
from uuid import UUID, uuid4
from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.sources.models import Source, SourceItem, idea_source_items_table
from app.sources.rss_provider import fetch_rss_items
from app.strategies.models import ContentStrategy, strategy_sources_table
from app.ideas.models import Idea, IdeaStatus
from app.ideas.scout_provider import execute_scout_and_score

logger = logging.getLogger(__name__)


def get_source(db: Session, source_id: UUID) -> Source:
    source = db.query(Source).filter(Source.id == source_id).first()
    if not source:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Source {source_id} not found."
        )
    return source


def sync_source(db: Session, source_id: UUID) -> dict[str, Any]:
    """
    Ingests source items from a configured source, deduplicates them against source_items,
    triggers scout & scoring for new items against linked strategies, and persists ideas.
    
    Deterministic code controls fetching, deduplication, and persistence.
    LLM/Evaluator handles synthesis and scoring.
    """
    source = get_source(db, source_id)
    if not source.enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Source {source_id} is disabled."
        )

    if source.source_type != "rss":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported source type: {source.source_type}. Discovery currently supports RSS."
        )

    if not source.url:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Source {source_id} has no URL configured."
        )

    # 1. Fetch raw items from RSS feed
    raw_items = fetch_rss_items(source.url)
    items_fetched = len(raw_items)

    # 2. Deduplicate: Find existing items for this source
    # Unique constraint is on (source_id, external_id)
    incoming_external_ids = [item["external_id"] for item in raw_items if item.get("external_id")]
    existing_records = (
        db.query(SourceItem.external_id)
        .filter(
            SourceItem.source_id == source_id,
            SourceItem.external_id.in_(incoming_external_ids),
        )
        .all()
    )
    existing_ids = {row[0] for row in existing_records}

    new_items_to_insert = [
        item for item in raw_items if item["external_id"] not in existing_ids
    ]

    inserted_source_items: list[SourceItem] = []
    for item in new_items_to_insert:
        si = SourceItem(
            id=uuid4(),
            source_id=source_id,
            external_id=item["external_id"],
            content_hash=item.get("content_hash"),
            title=item.get("title"),
            url=item.get("url"),
            content=item.get("description"),
            source_metadata={
                "author": item.get("author"),
                "published_at": item.get("published_at"),
                "raw_entry": item.get("raw_entry", {}),
            },
        )
        db.add(si)
        inserted_source_items.append(si)

    db.flush()  # assign IDs without committing entire transaction

    new_items_count = len(inserted_source_items)
    ideas_created_count = 0
    scout_log = None

    # 3. If there are new items, scout and score ideas for linked strategies
    if inserted_source_items:
        # Find linked content strategies
        stmt = (
            select(ContentStrategy)
            .join(
                strategy_sources_table,
                ContentStrategy.id == strategy_sources_table.c.strategy_id,
            )
            .where(
                strategy_sources_table.c.source_id == source_id,
                ContentStrategy.enabled.is_(True),
            )
        )
        strategies = db.execute(stmt).scalars().all()

        for strat in strategies:
            # Prepare items for scout prompt
            items_payload = [
                {
                    "title": si.title,
                    "url": si.url,
                    "description": si.content,
                }
                for si in inserted_source_items
            ]

            scored_ideas, prompt, response = execute_scout_and_score(
                strategy_name=strat.name,
                strategy_config=strat.config,
                items=items_payload,
            )
            scout_log = {"prompt": prompt, "response": response}

            for idea_dict in scored_ideas:
                idea = Idea(
                    id=uuid4(),
                    strategy_id=strat.id,
                    title=idea_dict["title"],
                    description=idea_dict["description"],
                    status=IdeaStatus.NEW,
                    relevance_score=idea_dict["relevance_score"],
                    trend_score=idea_dict["trend_score"],
                    novelty_score=idea_dict["novelty_score"],
                    audience_fit_score=idea_dict["audience_fit_score"],
                    source_quality_score=idea_dict["source_quality_score"],
                    final_score=idea_dict["final_score"],
                    scoring_metadata=idea_dict["scoring_metadata"],
                )
                db.add(idea)
                db.flush()

                # Link idea to the source items that backed it
                indices = idea_dict.get("source_item_indices", [])
                for idx in indices:
                    if 0 <= idx < len(inserted_source_items):
                        backing_si = inserted_source_items[idx]
                        db.execute(
                            idea_source_items_table.insert().values(
                                id=uuid4(),
                                idea_id=idea.id,
                                source_item_id=backing_si.id,
                            )
                        )
                ideas_created_count += 1

    db.commit()

    return {
        "source_id": str(source_id),
        "source_name": source.name,
        "items_fetched": items_fetched,
        "new_items_count": new_items_count,
        "ideas_created_count": ideas_created_count,
        "scout_log": scout_log,
    }
