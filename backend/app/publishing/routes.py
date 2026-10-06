from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.publishing.models import Publication
from app.analytics.models import Analytics
from app.publishing.schemas import PublicationResponse, AnalyticsResponse, ManualMetricsInput
from datetime import datetime, timezone

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


@router.post("/{id}/analytics/manual", response_model=AnalyticsResponse, status_code=status.HTTP_201_CREATED)
def add_manual_analytics_endpoint(
    id: UUID,
    data: ManualMetricsInput,
    db: Session = Depends(get_db),
):
    """
    CP-1.5: Records a manual snapshot for a publication with provider='manual'.
    Non-negative integers validated by schema.
    """
    pub = db.query(Publication).filter(Publication.id == id).first()
    if not pub:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Publication {id} not found."
        )

    # Validation: non-negative integers
    for field_name in ["impressions", "reactions", "comments", "clicks", "shares"]:
        val = getattr(data, field_name)
        if val < 0:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Field '{field_name}' must be non-negative (received {val})."
            )

    total_engagements = data.reactions + data.comments + data.clicks + data.shares
    rate = round(total_engagements / data.impressions, 4) if data.impressions > 0 else 0.0

    snapshot = Analytics(
        publication_id=pub.id,
        metrics={
            "impressions": data.impressions,
            "reactions": data.reactions,
            "likes": data.reactions,
            "comments": data.comments,
            "clicks": data.clicks,
            "shares": data.shares,
            "engagement_rate": rate,
            "provider": "manual",
            "is_stub": False,
            "is_initial": False,
        },
        collected_at=datetime.now(timezone.utc),
    )
    db.add(snapshot)
    db.commit()
    db.refresh(snapshot)
    return snapshot

