import os
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from app.strategies.models import ContentStrategy
from app.publishing.models import Publication
from app.scheduler.models import ScheduledJob

# Backoff delays in minutes after publishing
ANALYTICS_BACKOFF_MINUTES = [15, 60, 360, 1440, 4320, 10080]  # 15m, 1h, 6h, 24h, 72h, 7d
# Buffer refreshes post metrics about once a day, so after the ladder keep checking daily
# for ANALYTICS_POLL_WINDOW_DAYS after publication. Without this, posts older than a week
# never show their later numbers.
ANALYTICS_DAILY_POLL_MINUTES = 1440
ANALYTICS_POLL_WINDOW_DAYS = 30


def get_min_discovery_interval_hours() -> float:
    """Returns minimum interval for discovery in hours (default 1.0, overridable via env for testing)."""
    val = os.getenv("MIN_DISCOVERY_INTERVAL_HOURS", "1.0")
    try:
        return float(val)
    except ValueError:
        return 1.0


def is_strategy_discovery_due(
    strategy: ContentStrategy,
    last_run_time: datetime | None,
    now: datetime | None = None,
) -> bool:
    """
    Determines if a strategy is due for scheduled discovery:
    - Must be enabled.
    - Must have discovery_interval_hours configured in config (> 0).
    - If never run before, it is due.
    - If last run was more than interval hours ago, it is due.
    - Enforces MIN_DISCOVERY_INTERVAL_HOURS lower bound.
    """
    if not strategy.enabled:
        return False

    config = strategy.config or {}
    interval_hours = config.get("discovery_interval_hours")
    if interval_hours is None or float(interval_hours) <= 0:
        return False

    interval_hours = float(interval_hours)
    min_interval = get_min_discovery_interval_hours()
    effective_interval = max(interval_hours, min_interval)

    if last_run_time is None:
        return True

    now = now or datetime.now(timezone.utc)
    # Ensure timezone aware
    if last_run_time.tzinfo is None:
        last_run_time = last_run_time.replace(tzinfo=timezone.utc)

    return (now - last_run_time) >= timedelta(hours=effective_interval)


def get_next_analytics_sync_time(
    publication: Publication,
    sync_attempt_count: int,
    last_attempt_time: datetime | None = None,
) -> datetime | None:
    """
    Computes the scheduled time for the next analytics sync attempt:
    - Skips publications that are not PUBLISHED or have no external_id.
    - If publication has an initial/stub indicator without real ID, skip.
    - After the ladder, checks daily until the 30-day window after publication closes.
    - If last_attempt_time is provided and attempts > 0, next time is computed
      from the last attempt using the step's interval, or from published_at
      if last_attempt_time is not set.
    """
    if publication.status.value != "PUBLISHED" or not publication.external_id:
        return None
    # Gone from the platform: nothing left to measure.
    from app.analytics.upstream import deleted_upstream_at
    if deleted_upstream_at(publication):
        return None

    # Never touches publications that are stubs or test mocks (per CP-2B: "Never touches publications that are stubs or have no external ID")
    ext_id = publication.external_id.strip()
    # buffer_idea_* is not a Buffer post id (Buffer answers "Invalid PostId format").
    if ext_id.startswith(("linkedin_", "test-ext-", "stub_", "buffer_idea_")):
        return None

    published = publication.published_at or publication.created_at
    if published.tzinfo is None:
        published = published.replace(tzinfo=timezone.utc)
    window_end = published + timedelta(days=ANALYTICS_POLL_WINDOW_DAYS)

    if sync_attempt_count >= len(ANALYTICS_BACKOFF_MINUTES):
        # Past the ladder: one check a day until the window closes.
        anchor = last_attempt_time or published
        if anchor.tzinfo is None:
            anchor = anchor.replace(tzinfo=timezone.utc)
        next_time = anchor + timedelta(minutes=ANALYTICS_DAILY_POLL_MINUTES)
        return next_time if next_time <= window_end else None

    delay_minutes = ANALYTICS_BACKOFF_MINUTES[sync_attempt_count]

    if last_attempt_time is not None and sync_attempt_count > 0:
        base_time = last_attempt_time
    else:
        base_time = published

    if base_time.tzinfo is None:
        base_time = base_time.replace(tzinfo=timezone.utc)

    next_time = base_time + timedelta(minutes=delay_minutes)
    return next_time if next_time <= window_end else None

