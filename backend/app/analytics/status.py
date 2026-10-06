"""
One analytics status per publication, derived from the most recent attempt.

The UI shows exactly one status block. States:

    available         a valid Buffer snapshot exists (numbers are real)
    manual            the latest valid snapshot was entered by hand
    not_collected_yet Buffer answered and has no metrics for this post yet
    network_error     this server could not reach Buffer; nothing was checked
    failed            the last sync attempt failed with a provider error
    none              no attempt yet and no valid snapshot

Timestamps are UTC ISO strings. The frontend formats them with a zone label.
"""
import json
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.analytics.models import Analytics
from app.analytics.service import NETWORK_ERROR_STATE
from app.publishing.models import Publication
from app.scheduler.service import get_publication_sync_schedule_info

MANUAL_SYNC_KEY = "last_manual_sync"


def record_manual_sync_attempt(
    db: Session,
    publication_id: UUID,
    outcome: str,
    message: str | None = None,
    technical: str | None = None,
) -> None:
    """
    Records a manual Sync Metrics click outcome on the publication. A single UPDATE
    with jsonb_set, so it cannot race the scheduler or another click.
    """
    value = {
        "at": datetime.now(timezone.utc).isoformat(),
        "outcome": outcome,
        "message": message,
        "technical": technical,
    }
    db.execute(
        text(
            "UPDATE publications "
            "SET publication_metadata = jsonb_set(COALESCE(publication_metadata, '{}'::jsonb), "
            "    CAST(:path AS text[]), CAST(:value AS jsonb)) "
            "WHERE id = :id"
        ),
        {"path": "{" + MANUAL_SYNC_KEY + "}", "value": json.dumps(value), "id": publication_id},
    )
    db.commit()


def _latest_valid_snapshot(db: Session, publication_id: UUID) -> Analytics | None:
    """Newest snapshot that is real: not a stub, not quarantined."""
    return (
        db.query(Analytics)
        .filter(
            Analytics.publication_id == publication_id,
            text("COALESCE((metrics->>'is_stub')::boolean, false) IS FALSE"),
            text("metrics->>'invalid_reason' IS NULL"),
        )
        .order_by(Analytics.collected_at.desc())
        .first()
    )


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value)


def build_analytics_status(db: Session, publication: Publication) -> dict[str, Any]:
    schedule = get_publication_sync_schedule_info(db, publication)
    valid = _latest_valid_snapshot(db, publication.id)
    manual = (publication.publication_metadata or {}).get(MANUAL_SYNC_KEY)

    # Most recent attempt: scheduler job or manual click, whichever is newer.
    candidates = []
    if schedule["last_attempt_at"]:
        candidates.append({
            "at": schedule["last_attempt_at"],
            "outcome": schedule["last_attempt_outcome"],
            "message": schedule["last_attempt_error"],
            "technical": None,
            "source": "scheduler",
        })
    if manual:
        candidates.append({**manual, "source": "manual"})
    last_attempt = max(candidates, key=lambda c: _parse_iso(c["at"]), default=None)

    # Buffer answered (ready or not_ready) at this time. Network failures never count.
    last_buffer_response_at = schedule["last_buffer_response_at"]
    if manual and manual.get("outcome") in ("ready", "not_ready"):
        manual_at = _parse_iso(manual["at"])
        scheduled_at = _parse_iso(last_buffer_response_at)
        if scheduled_at is None or manual_at > scheduled_at:
            last_buffer_response_at = manual["at"]

    manual_snapshot_newer = bool(
        valid and valid.metrics.get("provider") == "manual"
        and (last_attempt is None or valid.collected_at > _parse_iso(last_attempt["at"]))
    )

    if manual_snapshot_newer:
        state = "manual"
    elif last_attempt is None:
        state = "available" if valid else "none"
    else:
        outcome = last_attempt["outcome"]
        if outcome in ("ready",):
            state = "available" if valid else "failed"
        elif outcome == "not_ready":
            state = "not_collected_yet"
        elif outcome == NETWORK_ERROR_STATE:
            state = NETWORK_ERROR_STATE
        else:
            state = "failed"

    return {
        "state": state,
        "last_attempt_at": last_attempt["at"] if last_attempt else None,
        "last_attempt_outcome": last_attempt["outcome"] if last_attempt else None,
        "last_attempt_source": last_attempt["source"] if last_attempt else None,
        "last_attempt_message": last_attempt.get("message") if last_attempt else None,
        "last_attempt_technical": last_attempt.get("technical") if last_attempt else None,
        "last_buffer_response_at": last_buffer_response_at,
        "attempt_number": schedule["attempt_number"],
        "network_failures_in_row": schedule["network_failures_in_row"],
        "network_retry_paused": schedule["network_retry_paused"],
        "next_sync_at": schedule["next_sync_at"],
        "next_sync_overdue": schedule["next_sync_overdue"],
        "scheduler_running": schedule["scheduler_running"],
        "valid_snapshot": {
            "id": str(valid.id),
            "collected_at": valid.collected_at.isoformat(),
            "provider": valid.metrics.get("provider"),
        } if valid else None,
    }
