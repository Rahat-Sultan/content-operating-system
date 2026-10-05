import logging
from uuid import UUID
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.analytics.models import Analytics
from app.analytics.interface import (
    AnalyticsRequest,
    PermanentAnalyticsError,
    TransientAnalyticsError,
    MetricsNotAvailableError,
)
from app.analytics.factory import get_analytics_provider
from app.publishing.models import Publication, PublicationStatus

logger = logging.getLogger(__name__)


def sync_publication_metrics(db: Session, publication_id: UUID) -> Analytics:
    """
    Synchronizes metrics for a publication:
    1. Loads the publication, confirms status == PUBLISHED.
       (Rejects PENDING/PUBLISHING/FAILED with 400 Bad Request).
    2. Validates that external_id is present.
    3. Calls the configured AnalyticsProvider to fetch live metrics.
    4. Appends a new historical snapshot row into analytics table (never overwriting previous rows).
    5. Returns the newly created Analytics record.
    """
    pub = db.query(Publication).filter(Publication.id == publication_id).first()
    if not pub:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Publication {publication_id} not found."
        )

    if pub.status != PublicationStatus.PUBLISHED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot sync analytics for publication in '{pub.status.value}' status. Publication must be 'PUBLISHED'."
        )

    if not pub.external_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Publication {publication_id} does not have an external_id to sync metrics for."
        )

    provider = get_analytics_provider()
    request = AnalyticsRequest(
        publication_id=pub.id,
        platform=pub.platform,
        external_post_id=pub.external_id,
        metadata=pub.publication_metadata or {},
    )

    try:
        result = provider.fetch_metrics(request)
    except MetricsNotAvailableError as not_ready_err:
        logger.info("Metrics not ready for publication %s: %s", publication_id, not_ready_err)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Metrics not yet available: Buffer is still indexing this post. Please try again shortly.",
        ) from not_ready_err
    except PermanentAnalyticsError as perm_err:
        logger.error("Permanent error syncing metrics for publication %s: %s", publication_id, perm_err)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Analytics provider rejected request: {perm_err}",
        ) from perm_err
    except TransientAnalyticsError as trans_err:
        logger.error("Transient error syncing metrics for publication %s: %s", publication_id, trans_err)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Analytics provider temporarily unavailable: {trans_err}",
        ) from trans_err
    except Exception as exc:
        logger.error("Unexpected error syncing metrics for publication %s: %s", publication_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to sync publication analytics: {exc}",
        ) from exc

    # Insert a new historical snapshot row (never overwrite existing rows)
    snapshot = Analytics(
        publication_id=pub.id,
        metrics=result.metrics,
        collected_at=result.collected_at,
    )
    db.add(snapshot)
    db.commit()
    db.refresh(snapshot)

    logger.info(
        "Successfully recorded analytics snapshot %s for publication %s (provider=%s, is_stub=%s)",
        snapshot.id,
        pub.id,
        result.provider,
        result.is_stub,
    )
    return snapshot
