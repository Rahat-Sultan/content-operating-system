from fastapi import HTTPException
from uuid import UUID
from typing import Any
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.sources.schemas import CreateSourceRequest, UpdateSourceRequest, SourceResponse
from app.sources.service import sync_source, get_source, create_source, update_source

router = APIRouter(prefix="/sources", tags=["sources"])


@router.post("/{id}/sync")
def sync_source_endpoint(
    id: UUID,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """
    Triggers deterministic ingestion & deduplication for an RSS source,
    followed by scout & structured scoring for newly ingested items.
    """
    return sync_source(db=db, source_id=id)


@router.get("", response_model=list[SourceResponse])
def list_sources_endpoint(
    db: Session = Depends(get_db),
):
    from app.sources.models import Source
    return db.query(Source).order_by(Source.created_at.desc()).all()


@router.post("", response_model=SourceResponse, status_code=status.HTTP_201_CREATED)
def create_source_endpoint(
    request: CreateSourceRequest,
    db: Session = Depends(get_db),
):
    """
    Create a new content source (e.g. RSS feed).
    """
    try:
        return create_source(
            db=db,
            name=request.name,
            source_type=request.source_type,
            url=request.url,
            enabled=request.enabled,
            config=request.config,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.get("/{id}", response_model=SourceResponse)
def get_source_endpoint(
    id: UUID,
    db: Session = Depends(get_db),
):
    return get_source(db=db, source_id=id)


@router.patch("/{id}", response_model=SourceResponse)
def update_source_endpoint(
    id: UUID,
    request: UpdateSourceRequest,
    db: Session = Depends(get_db),
):
    return update_source(
        db=db,
        source_id=id,
        name=request.name,
        source_type=request.source_type,
        url=request.url,
        enabled=request.enabled,
        config=request.config,
    )
