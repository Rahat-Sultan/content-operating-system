from datetime import datetime, timezone
import logging
import random
from app.analytics.interface import (
    AnalyticsProvider,
    AnalyticsRequest,
    AnalyticsResult,
)

logger = logging.getLogger(__name__)


class LocalTestAnalyticsProvider(AnalyticsProvider):
    """
    Local test analytics provider for when Buffer is not configured or in tests.
    Tags metrics with is_stub: true per Content OS conventions.
    """

    def fetch_metrics(self, request: AnalyticsRequest) -> AnalyticsResult:
        impressions = random.randint(1200, 5400)
        clicks = int(impressions * random.uniform(0.02, 0.06))
        likes = int(impressions * random.uniform(0.015, 0.045))
        comments = int(likes * random.uniform(0.08, 0.25))
        shares = int(likes * random.uniform(0.05, 0.15))

        metrics = {
            "impressions": impressions,
            "clicks": clicks,
            "likes": likes,
            "reactions": likes,
            "comments": comments,
            "shares": shares,
            "engagement_rate": round((likes + comments + shares) / max(impressions, 1), 4),
            "is_stub": True,
            "is_initial": False,
        }

        return AnalyticsResult(
            publication_id=request.publication_id,
            platform=request.platform,
            external_post_id=request.external_post_id,
            metrics=metrics,
            collected_at=datetime.now(timezone.utc),
            provider="local_test",
            is_stub=True,
        )
