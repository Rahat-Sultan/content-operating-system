import logging
from datetime import datetime, timezone
import random
from typing import Any
import uuid
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.analytics.models import Analytics

logger = logging.getLogger(__name__)


def generate_stub_metrics(is_initial: bool = True) -> dict[str, Any]:
    """
    Generates plausible engagement numbers tagged with is_stub: True and is_initial flag.
    """
    impressions = random.randint(1200, 5400)
    clicks = int(impressions * random.uniform(0.02, 0.06))
    likes = int(impressions * random.uniform(0.015, 0.045))
    comments = int(likes * random.uniform(0.08, 0.25))
    shares = int(likes * random.uniform(0.05, 0.15))

    return {
        "is_stub": True,
        "is_initial": is_initial,
        "impressions": impressions,
        "clicks": clicks,
        "likes": likes,
        "comments": comments,
        "shares": shares,
        "engagement_rate": round((likes + comments + shares) / max(impressions, 1), 4),
    }


def record_stub_analytics(db: Session, publication_id: uuid.UUID, is_initial: bool = True) -> Analytics:
    """
    Inserts a realistic stub metrics row for a publication into the analytics table.
    Enforces that concurrent workers attempting to record the initial publish-time snapshot
    do not create duplicate rows: catches UniqueViolation from uq_initial_analytics_per_publication
    and gracefully reuses the existing winning record.
    """
    if is_initial:
        # Check if an initial snapshot already exists in DB
        existing = (
            db.query(Analytics)
            .filter(
                Analytics.publication_id == publication_id,
                Analytics.metrics["is_initial"].astext == "true",
            )
            .first()
        )
        if existing:
            return existing

    analytics_row = Analytics(
        id=uuid.uuid4(),
        publication_id=publication_id,
        metrics=generate_stub_metrics(is_initial=is_initial),
        collected_at=datetime.now(timezone.utc),
    )
    db.add(analytics_row)
    try:
        db.commit()
        db.refresh(analytics_row)
        return analytics_row
    except IntegrityError:
        # Caught concurrent race inserting initial snapshot
        db.rollback()
        winner = (
            db.query(Analytics)
            .filter(
                Analytics.publication_id == publication_id,
                Analytics.metrics["is_initial"].astext == "true",
            )
            .first()
        )
        if winner:
            logger.info("Concurrent initial analytics insert handled; returning winning snapshot %s", winner.id)
            return winner
        raise
