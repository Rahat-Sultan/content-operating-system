from uuid import UUID
from sqlalchemy.orm import Session
from sqlalchemy import select
from fastapi import HTTPException, status

from app.ideas.models import Idea, IdeaStatus
from app.sources.models import SourceItem, idea_source_items_table


def list_ideas(
    db: Session,
    status_filter: IdeaStatus | None = None,
    limit: int = 50,
    strategy_id: UUID | None = None,
    owner_id=None,
) -> list[Idea]:
    query = db.query(Idea)
    if owner_id is not None:
        query = query.filter(Idea.owner_id == owner_id)
    if status_filter:
        query = query.filter(Idea.status == status_filter)
    if strategy_id:
        query = query.filter(Idea.strategy_id == strategy_id)
    
    # Sort by final_score descending (nulls last)
    query = query.order_by(Idea.final_score.desc().nullslast(), Idea.created_at.desc())
    return query.limit(limit).all()


def get_idea(db: Session, idea_id: UUID, owner_id=None) -> Idea:
    query = db.query(Idea).filter(Idea.id == idea_id)
    if owner_id is not None:
        query = query.filter(Idea.owner_id == owner_id)
    idea = query.first()
    if not idea:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Idea {idea_id} not found."
        )
    return idea


def get_idea_sources(db: Session, idea_id: UUID, owner_id=None) -> list[SourceItem]:
    # Confirm idea exists (and belongs to this account)
    get_idea(db, idea_id, owner_id)

    # Join source_items through idea_source_items_table
    stmt = (
        select(SourceItem)
        .join(
            idea_source_items_table,
            SourceItem.id == idea_source_items_table.c.source_item_id,
        )
        .where(idea_source_items_table.c.idea_id == idea_id)
        .order_by(SourceItem.collected_at.desc())
    )
    results = db.execute(stmt).scalars().all()
    return list(results)

