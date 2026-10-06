import os
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from app.strategies.models import ContentStrategy
from app.publishing.models import Publication
from app.scheduler.models import ScheduledJob

# Backoff delays in minutes after publishing
ANALYTICS_BACKOFF_MINUTES = [15, 60, 360, 1440, 4320, 10080]  # 15m, 1h, 6h, 24h, 72h, 7d


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
    - After len(ANALYTICS_BACKOFF_MINUTES) attempts, stops (returns None).
    - If last_attempt_time is provided and attempts > 0, next time is computed
      from the last attempt using the step's interval, or from published_at
      if last_attempt_time is not set.
    """
    if publication.status.value != "PUBLISHED" or not publication.external_id:
        return None

    # Never touches publications that are stubs or test mocks (per CP-2B: "Never touches publications that are stubs or have no external ID")
    ext_id = publication.external_id.strip()
    if ext_id.startswith("linkedin_") or ext_id.startswith("test-ext-") or ext_id.startswith("stub_"):
        return None

    if sync_attempt_count >= len(ANALYTICS_BACKOFF_MINUTES):
        return None

    delay_minutes = ANALYTICS_BACKOFF_MINUTES[sync_attempt_count]

    if last_attempt_time is not None and sync_attempt_count > 0:
        base_time = last_attempt_time
    else:
        base_time = publication.published_at or publication.created_at

    if base_time.tzinfo is None:
        base_time = base_time.replace(tzinfo=timezone.utc)

    return base_time + timedelta(minutes=delay_minutes)

