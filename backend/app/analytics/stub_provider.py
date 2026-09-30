from datetime import datetime, timezone
import random
from typing import Any
import uuid
from sqlalchemy.orm import Session

from app.analytics.models import Analytics


def generate_stub_metrics() -> dict[str, Any]:
    """
    Generates plausible engagement numbers tagged with is_stub: True.
    """
    impressions = random.randint(1200, 5400)
    clicks = int(impressions * random.uniform(0.02, 0.06))
    likes = int(impressions * random.uniform(0.015, 0.045))
    comments = int(likes * random.uniform(0.08, 0.25))
    shares = int(likes * random.uniform(0.05, 0.15))

    return {
        "is_stub": True,
        "impressions": impressions,
        "clicks": clicks,
        "likes": likes,
        "comments": comments,
        "shares": shares,
        "engagement_rate": round((likes + comments + shares) / max(impressions, 1), 4),
    }


def record_stub_analytics(db: Session, publication_id: uuid.UUID) -> Analytics:
    """
    Inserts a realistic stub metrics row for a publication into the analytics table.
    """
    analytics_row = Analytics(
        id=uuid.uuid4(),
        publication_id=publication_id,
        metrics=generate_stub_metrics(),
        collected_at=datetime.now(timezone.utc),
    )
    db.add(analytics_row)
    db.commit()
    db.refresh(analytics_row)
    return analytics_row
