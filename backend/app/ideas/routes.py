from uuid import UUID
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.accounts.models import User
from app.accounts.service import current_user
from app.db import get_db
from app.ideas.models import IdeaStatus
from app.ideas.schemas import IdeaResponse, SourceItemSummary
from app.ideas.service import list_ideas, get_idea, get_idea_sources
from app.publishing.platforms import platforms_for_strategy_config
from app.strategies.models import ContentStrategy

router = APIRouter(prefix="/ideas", tags=["ideas"])


def _with_platforms(db: Session, ideas: list) -> list[IdeaResponse]:
    """Each idea carries its strategy's target platforms and name. One query for the whole list."""
    strategy_ids = {i.strategy_id for i in ideas}
    strategies = {
        s.id: s
        for s in db.query(ContentStrategy).filter(ContentStrategy.id.in_(strategy_ids)).all()
    } if strategy_ids else {}
    out = []
    for i in ideas:
        strat = strategies.get(i.strategy_id)
        out.append(IdeaResponse.model_validate(i).model_copy(update={
            "platforms": platforms_for_strategy_config(strat.config if strat else None),
            "strategy_name": strat.name if strat else None,
        }))
    return out


@router.get("", response_model=list[IdeaResponse])
def get_all_ideas(
    status: IdeaStatus | None = Query(None, description="Filter by IdeaStatus"),
    limit: int = Query(50, ge=1, le=500),
    strategy_id: UUID | None = Query(None, description="Only ideas from this strategy"),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    ideas = list_ideas(db=db, status_filter=status, limit=limit, strategy_id=strategy_id, owner_id=user.id)
    return _with_platforms(db, ideas)


@router.post("/{id}/archive", response_model=IdeaResponse)
def archive_idea_endpoint(id: UUID, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Moves a NEW or SELECTED idea to the Rejected archive. Reversible."""
    from app.ideas.lifecycle import archive_idea
    return _with_platforms(db, [archive_idea(db, id, user.id)])[0]


@router.post("/{id}/restore", response_model=IdeaResponse)
def restore_idea_endpoint(id: UUID, db: Session = Depends(get_db), user: User = Depends(current_user)):
    from app.ideas.lifecycle import restore_idea
    return _with_platforms(db, [restore_idea(db, id, user.id)])[0]


@router.delete("/{id}")
def delete_idea_endpoint(id: UUID, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Permanent. Refused (409) if the idea has any workflow run. Archive instead."""
    from app.ideas.lifecycle import delete_idea
    delete_idea(db, id, user.id)
    return {"deleted": str(id)}


@router.get("/{id}", response_model=IdeaResponse)
def get_single_idea(
    id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    return _with_platforms(db, [get_idea(db=db, idea_id=id, owner_id=user.id)])[0]


@router.get("/{id}/sources", response_model=list[SourceItemSummary])
def get_sources_for_idea(
    id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    return get_idea_sources(db=db, idea_id=id, owner_id=user.id)

