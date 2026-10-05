from uuid import UUID
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.strategies.schemas import (
    CreateStrategyRequest,
    UpdateStrategyRequest,
    StrategyResponse,
    SourceSummary,
    StrategyDiscoveryResult,
)
from app.strategies.service import (
    list_strategies,
    get_strategy,
    create_strategy,
    update_strategy,
    get_strategy_sources,
    run_strategy_discovery,
)

router = APIRouter(prefix="/strategies", tags=["strategies"])


def _to_strategy_response(strategy, sources, db: Session | None = None) -> StrategyResponse:
    schedule_info = None
    if db is not None:
        from app.scheduler.service import get_strategy_discovery_schedule_info
        schedule_info = get_strategy_discovery_schedule_info(db, strategy)

    return StrategyResponse(
        id=strategy.id,
        name=strategy.name,
        description=strategy.description,
        config=strategy.config,
        enabled=strategy.enabled,
        sources=[
            SourceSummary(
                id=s.id,
                name=s.name,
                source_type=s.source_type,
                url=s.url,
                enabled=s.enabled,
            )
            for s in sources
        ],
        schedule_info=schedule_info,
        created_at=strategy.created_at,
        updated_at=strategy.updated_at,
    )


@router.get("", response_model=list[StrategyResponse])
def get_all_strategies(
    enabled_only: bool = Query(False, description="Filter to enabled strategies only"),
    db: Session = Depends(get_db),
):
    """
    List content strategies.
    """
    strategies = list_strategies(db, enabled_only=enabled_only)
    result = []
    for strat in strategies:
        sources = get_strategy_sources(db, strat.id)
        result.append(_to_strategy_response(strat, sources, db=db))
    return result


@router.post("", response_model=StrategyResponse, status_code=status.HTTP_201_CREATED)
def create_new_strategy(
    request: CreateStrategyRequest,
    db: Session = Depends(get_db),
):
    """
    Create a new content strategy with niche configuration and optional source links.
    """
    strategy = create_strategy(
        db=db,
        name=request.name,
        description=request.description,
        config=request.config,
        enabled=request.enabled,
        source_ids=request.source_ids,
    )
    sources = get_strategy_sources(db, strategy.id)
    return _to_strategy_response(strategy, sources, db=db)


@router.get("/{id}", response_model=StrategyResponse)
def get_single_strategy(
    id: UUID,
    db: Session = Depends(get_db),
):
    """
    Get strategy detail and associated sources by strategy ID.
    """
    strategy = get_strategy(db, id)
    sources = get_strategy_sources(db, strategy.id)
    return _to_strategy_response(strategy, sources, db=db)


@router.patch("/{id}", response_model=StrategyResponse)
def update_existing_strategy(
    id: UUID,
    request: UpdateStrategyRequest,
    db: Session = Depends(get_db),
):
    """
    Update editable configuration, enabled status, or associated sources for a strategy.
    """
    strategy = update_strategy(
        db=db,
        strategy_id=id,
        name=request.name,
        description=request.description,
        config=request.config,
        enabled=request.enabled,
        source_ids=request.source_ids,
    )
    sources = get_strategy_sources(db, strategy.id)
    return _to_strategy_response(strategy, sources, db=db)


@router.post("/{id}/discover", response_model=StrategyDiscoveryResult)
def trigger_strategy_discovery(
    id: UUID,
    db: Session = Depends(get_db),
):
    """
    Triggers Discovery for this specific strategy:
    Ingests attached sources and runs scout+scoring producing new candidate Ideas.
    """
    return run_strategy_discovery(db=db, strategy_id=id)
