import logging
from typing import Any
from uuid import UUID, uuid4
from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import delete, select

from app.strategies.models import ContentStrategy, strategy_sources_table
from app.sources.models import Source, SourceItem, idea_source_items_table
from app.sources.rss_provider import fetch_rss_items
from app.ideas.lifecycle import add_new_idea_if_unique
from app.ideas.models import Idea, IdeaStatus
from app.ideas.scout_provider import execute_scout_and_score

logger = logging.getLogger(__name__)


def list_strategies(db: Session, enabled_only: bool = False, owner_id=None) -> list[ContentStrategy]:
    query = db.query(ContentStrategy)
    if owner_id is not None:
        query = query.filter(ContentStrategy.owner_id == owner_id)
    if enabled_only:
        query = query.filter(ContentStrategy.enabled.is_(True))
    return query.order_by(ContentStrategy.created_at.desc()).all()


def get_strategy(db: Session, strategy_id: UUID, owner_id=None) -> ContentStrategy:
    query = db.query(ContentStrategy).filter(ContentStrategy.id == strategy_id)
    if owner_id is not None:
        query = query.filter(ContentStrategy.owner_id == owner_id)
    strategy = query.first()
    if not strategy:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"ContentStrategy {strategy_id} not found."
        )
    return strategy


def get_strategy_sources(db: Session, strategy_id: UUID) -> list[Source]:
    """Retrieve all Sources attached to a Strategy via strategy_sources."""
    stmt = (
        select(Source)
        .join(
            strategy_sources_table,
            Source.id == strategy_sources_table.c.source_id,
        )
        .where(strategy_sources_table.c.strategy_id == strategy_id)
        .order_by(Source.created_at.asc())
    )
    return list(db.execute(stmt).scalars().all())


def sync_strategy_source_links(db: Session, strategy_id: UUID, target_source_ids: list[UUID]) -> None:
    """Synchronizes strategy_sources join table rows for this strategy."""
    # Delete existing links
    db.execute(
        delete(strategy_sources_table).where(strategy_sources_table.c.strategy_id == strategy_id)
    )
    # Insert new links
    for s_id in set(target_source_ids):
        # Validate that the source exists
        source_exists = db.query(Source.id).filter(Source.id == s_id).first()
        if source_exists:
            db.execute(
                strategy_sources_table.insert().values(
                    id=uuid4(),
                    strategy_id=strategy_id,
                    source_id=s_id,
                )
            )


def create_strategy(
    db: Session,
    name: str,
    description: str | None = None,
    config: dict[str, Any] | None = None,
    enabled: bool = True,
    source_ids: list[UUID] | None = None,
    owner_id=None,
) -> ContentStrategy:
    strategy = ContentStrategy(
        id=uuid4(),
        owner_id=owner_id,
        name=name,
        description=description,
        config=config or {},
        enabled=enabled,
    )
    db.add(strategy)
    db.flush()

    if source_ids:
        sync_strategy_source_links(db, strategy.id, source_ids)

    db.commit()
    db.refresh(strategy)
    return strategy


def update_strategy(
    db: Session,
    strategy_id: UUID,
    name: str | None = None,
    description: str | None = None,
    config: dict[str, Any] | None = None,
    enabled: bool | None = None,
    source_ids: list[UUID] | None = None,
    owner_id=None,
) -> ContentStrategy:
    strategy = get_strategy(db, strategy_id, owner_id)

    if name is not None:
        strategy.name = name
    if description is not None:
        strategy.description = description
    if config is not None:
        strategy.config = config
    if enabled is not None:
        strategy.enabled = enabled

    if source_ids is not None:
        sync_strategy_source_links(db, strategy.id, source_ids)

    db.commit()
    db.refresh(strategy)
    return strategy


def run_strategy_discovery(
    db: Session,
    strategy_id: UUID,
    skip_llm_if_no_new_items: bool = False,
) -> dict[str, Any]:
    """
    Executes Discovery strictly for the specified Strategy:
    1. Loads the strategy and its attached Sources (isolated: ONLY this strategy's sources).
    2. Ingests & deduplicates RSS items for those sources using existing rss_provider.
    3. Runs scout & structured scoring using existing scout_provider with the strategy's niche/config.
    4. Persists generated Ideas linked to this strategy and backing source items.
    """
    strategy = get_strategy(db, strategy_id)
    if not strategy.enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Strategy {strategy_id} is disabled. Cannot run discovery."
        )

    sources = get_strategy_sources(db, strategy_id)
    if not sources:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Strategy '{strategy.name}' has no sources attached. Attach at least one source before running discovery."
        )

    total_items_fetched = 0
    total_new_items = 0
    created_ideas: list[Idea] = []

    for source in sources:
        if not source.enabled or source.source_type != "rss" or not source.url:
            continue

        raw_items = fetch_rss_items(source.url)
        total_items_fetched += len(raw_items)

        # Deduplicate incoming items against source_items for this source
        incoming_external_ids = [item["external_id"] for item in raw_items if item.get("external_id")]
        existing_records = (
            db.query(SourceItem.external_id)
            .filter(
                SourceItem.source_id == source.id,
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
                source_id=source.id,
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

        db.flush()
        total_new_items += len(inserted_source_items)

        # If new items exist, run scout & scoring for this Strategy
        # If skip_llm_if_no_new_items is True, skip calling the LLM when no new items arrived
        items_for_scouting = inserted_source_items
        if not items_for_scouting:
            if skip_llm_if_no_new_items:
                continue
            recent_items = (
                db.query(SourceItem)
                .filter(SourceItem.source_id == source.id)
                .order_by(SourceItem.collected_at.desc())
                .limit(5)
                .all()
            )
            items_for_scouting = recent_items

        if items_for_scouting:
            items_payload = [
                {
                    "title": si.title,
                    "url": si.url,
                    "description": si.content,
                }
                for si in items_for_scouting
            ]

            scored_ideas, prompt, response = execute_scout_and_score(
                strategy_name=strategy.name,
                strategy_config=strategy.config,
                items=items_payload,
            )

            for idea_dict in scored_ideas:
                idea = Idea(
                    id=uuid4(),
                    owner_id=strategy.owner_id,
                    strategy_id=strategy.id,
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
                if not add_new_idea_if_unique(db, idea):
                    continue  # this title is already proposed for the strategy

                # Link idea to the source items that backed it
                indices = idea_dict.get("source_item_indices", [])
                for idx in indices:
                    if 0 <= idx < len(items_for_scouting):
                        backing_si = items_for_scouting[idx]
                        db.execute(
                            idea_source_items_table.insert().values(
                                id=uuid4(),
                                idea_id=idea.id,
                                source_item_id=backing_si.id,
                            )
                        )
                created_ideas.append(idea)

    db.commit()

    return {
        "strategy_id": strategy.id,
        "strategy_name": strategy.name,
        "sources_synced": len(sources),
        "items_fetched": total_items_fetched,
        "new_items_count": total_new_items,
        "ideas_created_count": len(created_ideas),
        "created_idea_ids": [idea.id for idea in created_ideas],
    }
