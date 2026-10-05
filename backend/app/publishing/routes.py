from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.publishing.models import Publication
from app.analytics.models import Analytics
from app.publishing.schemas import PublicationResponse, AnalyticsResponse

router = APIRouter(prefix="/publications", tags=["publications"])


@router.get("/{id}", response_model=PublicationResponse)
def get_publication(
    id: UUID,
    db: Session = Depends(get_db),
):
    """
    Get publication record by ID.
    """
    publication = db.query(Publication).filter(Publication.id == id).first()
    if not publication:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Publication {id} not found."
        )
    return publication


@router.get("/{id}/analytics", response_model=list[AnalyticsResponse])
def get_publication_analytics(
    id: UUID,
    db: Session = Depends(get_db),
):
    """
    Get analytics performance snapshots for a publication by publication ID.
    Returns all historical snapshots, ordered by collection time descending.
    """
    publication = db.query(Publication).filter(Publication.id == id).first()
    if not publication:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Publication {id} not found."
        )

    records = (
        db.query(Analytics)
        .filter(Analytics.publication_id == id)
        .order_by(Analytics.collected_at.desc())
        .all()
    )
    return records


@router.post("/{id}/analytics/sync", response_model=AnalyticsResponse, status_code=status.HTTP_201_CREATED)
def sync_publication_analytics_endpoint(
    id: UUID,
    db: Session = Depends(get_db),
):
    """
    Manually triggers analytics sync for a published post.
    Calls configured analytics provider (e.g. Buffer) and appends a new historical snapshot.
    """
    from app.analytics.service import sync_publication_metrics
    return sync_publication_metrics(db=db, publication_id=id)
