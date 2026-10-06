"""
Durable queue entries for production workflow runs.

A start or a resume is a row in scheduled_jobs, written in the same transaction
as the state change that needs it. The scheduler worker claims the row and runs
the graph. If the backend process dies, the row survives and the worker picks it up.
"""
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.scheduler.models import ScheduledJob, JobType, JobStatus


def enqueue_workflow_job(
    db: Session,
    action: str,
    workflow_run_id: UUID,
    decision: dict[str, Any] | None = None,
) -> ScheduledJob:
    """Adds the job to the session. The caller commits, together with the state change."""
    if action not in ("start", "resume"):
        raise ValueError(f"Unknown workflow job action: {action}")
    payload: dict[str, Any] = {"action": action, "workflow_run_id": str(workflow_run_id)}
    if decision is not None:
        payload["decision"] = decision
    job = ScheduledJob(
        id=uuid4(),
        job_type=JobType.WORKFLOW_RUN,
        status=JobStatus.PENDING,
        scheduled_at=datetime.now(timezone.utc),
        payload=payload,
    )
    db.add(job)
    return job


def claim_run_start(db: Session, workflow_run_id: UUID) -> bool:
    """
    Atomic PENDING -> RUNNING. Returns False when the run is not PENDING, so a
    duplicate start job cannot run the same graph twice.
    """
    result = db.execute(
        text(
            "UPDATE workflow_runs SET status = 'RUNNING' "
            "WHERE id = :id AND status = 'PENDING'"
        ),
        {"id": workflow_run_id},
    )
    db.commit()
    return result.rowcount == 1
