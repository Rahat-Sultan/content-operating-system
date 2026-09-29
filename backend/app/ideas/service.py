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
) -> list[Idea]:
    query = db.query(Idea)
    if status_filter:
        query = query.filter(Idea.status == status_filter)
    
    # Sort by final_score descending (nulls last)
    query = query.order_by(Idea.final_score.desc().nullslast(), Idea.created_at.desc())
    return query.limit(limit).all()


def get_idea(db: Session, idea_id: UUID) -> Idea:
    idea = db.query(Idea).filter(Idea.id == idea_id).first()
    if not idea:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Idea {idea_id} not found."
        )
    return idea


def get_idea_sources(db: Session, idea_id: UUID) -> list[SourceItem]:
    # Confirm idea exists
    get_idea(db, idea_id)

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

