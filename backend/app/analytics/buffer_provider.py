from datetime import datetime, timezone
import logging
import os
from typing import Any
import httpx

from app.config import settings
from app.accounts.context import active_key
from app.analytics.interface import (
    AnalyticsProvider,
    AnalyticsRequest,
    AnalyticsResult,
    PermanentAnalyticsError,
    TransientAnalyticsError,
    NetworkAnalyticsError,
    MetricsNotAvailableError,
    MetricsUnsupportedError,
    PostNotFoundError,
)

logger = logging.getLogger(__name__)

BUFFER_GRAPHQL_ENDPOINT = "https://api.buffer.com"

# The only metric types an uncollected placeholder carries (verified 2026-10-06 against
# real responses; see DECISIONS.md ADR-018). Anything else means Buffer collected data.
PLACEHOLDER_METRIC_TYPES = frozenset({"reactions", "comments"})


def _metric_type(metric: dict[str, Any]) -> str:
    return (metric.get("type") or "").lower()


def build_post_metrics_query(post_id: str) -> str:
    return f"""{{
  post(input: {{ id: "{post_id}" }}) {{
    id
    status
    sentAt
    metricsUpdatedAt
    metrics {{
      name
      type
      value
      unit
      description
    }}
  }}
}}"""


class BufferAnalyticsProvider(AnalyticsProvider):
    """
    Real Buffer analytics provider using Buffer's GraphQL API.
    Queries the Post object by external_post_id to retrieve engagement metrics
    (reactions/likes, comments, clicks, impressions).
    """

    def __init__(self, access_token: str | None = None, timeout: float = 20.0):
        self.access_token = (access_token or active_key("BUFFER_ACCESS_TOKEN") or "").strip()
        self.timeout = timeout

    def _execute_graphql(self, query: str) -> dict[str, Any]:
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }
        payload = {"query": query}

        try:
            with httpx.Client(timeout=self.timeout) as client:
                res = client.post(BUFFER_GRAPHQL_ENDPOINT, headers=headers, json=payload)
        except (httpx.TimeoutException, httpx.NetworkError) as net_err:
            logger.error("Network error communicating with Buffer GraphQL API for analytics: %s", net_err)
            raise NetworkAnalyticsError(f"Network error querying Buffer analytics: {net_err}") from net_err

        if res.status_code == 429:
            raise TransientAnalyticsError(f"Buffer rate limit exceeded (HTTP 429): {res.text[:200]}")
        if res.status_code >= 500:
            raise TransientAnalyticsError(f"Buffer internal server error (HTTP {res.status_code}): {res.text[:200]}")
        if res.status_code in (401, 403):
            raise PermanentAnalyticsError(f"Buffer authentication failed (HTTP {res.status_code}): {res.text[:200]}")
        if res.status_code != 200:
            raise PermanentAnalyticsError(f"Buffer unexpected HTTP error (HTTP {res.status_code}): {res.text[:200]}")

        try:
            data = res.json()
        except Exception as j_err:
            raise PermanentAnalyticsError(f"Failed to parse Buffer GraphQL JSON: {j_err} (raw: {res.text[:200]})") from j_err

        return data

    def fetch_metrics(self, request: AnalyticsRequest) -> AnalyticsResult:
        """
        Fetches live metrics from Buffer for the post.
        """
        post_id = request.external_post_id.strip()
        if not post_id:
            raise PermanentAnalyticsError("No external_post_id provided on publication to query Buffer.")

        data = self._execute_graphql(build_post_metrics_query(post_id))
        errors = data.get("errors")
        if errors:
            err_msg = errors[0].get("message", "Unknown GraphQL error")
            err_code = errors[0].get("extensions", {}).get("code", "")
            logger.error("Buffer GraphQL error fetching metrics for post %s: %s (code=%s)", post_id, err_msg, err_code)
            if "not found" in err_msg.lower() or err_code == "NOT_FOUND":
                raise PostNotFoundError(
                    f"Post '{post_id}' not found on Buffer (permanent 404). Please verify external post ID."
                )
            raise PermanentAnalyticsError(f"Buffer analytics query error: {err_msg}")

        post_data = data.get("data", {}).get("post")
        if not post_data:
            raise MetricsNotAvailableError(
                f"Metrics for post '{post_id}' are not yet indexed by Buffer. Please try again shortly."
            )

        sent_at_str = post_data.get("sentAt")
        metrics_updated_at_str = post_data.get("metricsUpdatedAt")

        if not metrics_updated_at_str:
            raise MetricsNotAvailableError(
                f"Buffer has not yet updated metrics for post '{post_id}' (metricsUpdatedAt is null). Please try again shortly."
            )

        raw_metrics_list = post_data.get("metrics") or []

        # Gate on the metric shape, not on timestamps. metricsUpdatedAt is the time of the
        # last Buffer ingestion, not evidence of collected data: placeholder responses
        # (Reactions/Comments at zero) carry metricsUpdatedAt > sentAt, so a timestamp gate
        # accepts them. Only a response that reports something beyond Reactions/Comments
        # (e.g. Impressions, Reach) has collected data.
        if not raw_metrics_list:
            raise MetricsNotAvailableError(
                f"Buffer returned no metrics for post '{post_id}' yet."
            )
        if not any(_metric_type(m) not in PLACEHOLDER_METRIC_TYPES for m in raw_metrics_list):
            raise MetricsNotAvailableError(
                f"Buffer reports only Reactions and Comments for post '{post_id}' "
                f"(no impression data yet). Treated as uncollected."
            )

        metrics_dict: dict[str, Any] = {
            "is_stub": False,
            "is_initial": False,
            "provider": "buffer",
            "post_status": post_data.get("status"),
            "sent_at": sent_at_str,
            "metrics_updated_at": metrics_updated_at_str,
            "raw_metrics": raw_metrics_list,
            # Standardized fields with sensible defaults
            "reactions": 0,
            "likes": 0,
            "comments": 0,
            "clicks": 0,
            "shares": 0,
            "impressions": 0,
        }

        # Parse specific metric names/types from Buffer response
        for m in raw_metrics_list:
            m_name = (m.get("name") or "").lower()
            m_type = (m.get("type") or "").lower()
            val = m.get("value", 0)

            if "reaction" in m_name or "reaction" in m_type or "like" in m_name:
                metrics_dict["reactions"] = val
                metrics_dict["likes"] = val
            elif "comment" in m_name or "comment" in m_type:
                metrics_dict["comments"] = val
            elif "click" in m_name or "click" in m_type:
                metrics_dict["clicks"] = val
            elif "share" in m_name or "repost" in m_name or "share" in m_type:
                metrics_dict["shares"] = val
            elif "impression" in m_name or "view" in m_name:
                metrics_dict["impressions"] = val

        # Calculate engagement rate if impressions > 0
        total_engagements = metrics_dict["reactions"] + metrics_dict["comments"] + metrics_dict["shares"] + metrics_dict["clicks"]
        if metrics_dict["impressions"] > 0:
            metrics_dict["engagement_rate"] = round(total_engagements / metrics_dict["impressions"], 4)
        else:
            metrics_dict["engagement_rate"] = 0.0

        return AnalyticsResult(
            publication_id=request.publication_id,
            platform=request.platform,
            external_post_id=post_id,
            metrics=metrics_dict,
            collected_at=datetime.now(timezone.utc),
            provider="buffer",
            is_stub=False,
        )
