from uuid import UUID
from typing import Any
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.sources.service import sync_source, get_source

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


@router.get("/{id}")
def get_source_endpoint(
    id: UUID,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    source = get_source(db=db, source_id=id)
    return {
        "id": str(source.id),
        "name": source.name,
        "source_type": source.source_type,
        "url": source.url,
        "enabled": source.enabled,
        "config": source.config,
    }
