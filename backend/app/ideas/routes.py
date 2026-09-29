from uuid import UUID
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.ideas.models import IdeaStatus
from app.ideas.schemas import IdeaResponse, SourceItemSummary
from app.ideas.service import list_ideas, get_idea, get_idea_sources

router = APIRouter(prefix="/ideas", tags=["ideas"])


@router.get("", response_model=list[IdeaResponse])
def get_all_ideas(
    status: IdeaStatus | None = Query(None, description="Filter by IdeaStatus"),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
):
    return list_ideas(db=db, status_filter=status, limit=limit)


@router.get("/{id}", response_model=IdeaResponse)
def get_single_idea(
    id: UUID,
    db: Session = Depends(get_db),
):
    return get_idea(db=db, idea_id=id)


@router.get("/{id}/sources", response_model=list[SourceItemSummary])
def get_sources_for_idea(
    id: UUID,
    db: Session = Depends(get_db),
):
    return get_idea_sources(db=db, idea_id=id)

