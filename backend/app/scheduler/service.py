import logging
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID, uuid4
from fastapi import HTTPException

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.strategies.models import ContentStrategy
from app.publishing.models import Publication, PublicationStatus
from app.scheduler.models import ScheduledJob, JobType, JobStatus
from app.scheduler.schedule_calculator import (
    is_strategy_discovery_due,
    get_next_analytics_sync_time,
)
from app.strategies.service import run_strategy_discovery
from app.analytics.service import sync_publication_metrics, NETWORK_ERROR_STATE
from app.scheduler.heartbeat import write_heartbeat, scheduler_running
from app.scheduler.lease import LeaseKeeper
from app.scheduler.workflow_jobs import claim_run_start

logger = logging.getLogger("scheduler")

# Stale claim lease timeout: 5 minutes
STALE_CLAIM_TIMEOUT_MINUTES = 5

# A network failure (we could not reach Buffer) is retried after this delay...
NETWORK_RETRY_DELAY = timedelta(minutes=5)
# ...and automatic retries pause after this many failures in a row (about one hour).
# A successful sync, manual or scheduled, resets the count.
NETWORK_RETRY_LIMIT = 12


def _counts_as_ladder_attempt():
    """
    Analytics sync jobs that consume a rung of the metrics retry ladder.
    A network failure never reached the provider, so it must not consume one.
    """
    return func.coalesce(ScheduledJob.result["status"].astext, "") != NETWORK_ERROR_STATE


def consecutive_network_failures(db: Session, publication_id: UUID) -> tuple[int, datetime | None]:
    """Returns (failures in a row, time of the most recent one) for a publication's analytics syncs."""
    recent = (
        db.query(ScheduledJob)
        .filter(
            ScheduledJob.job_type == JobType.ANALYTICS_SYNC,
            ScheduledJob.publication_id == publication_id,
            ScheduledJob.status.in_([JobStatus.COMPLETED, JobStatus.FAILED]),
        )
        .order_by(ScheduledJob.completed_at.desc().nulls_last())
        .limit(NETWORK_RETRY_LIMIT + 1)
        .all()
    )
    count = 0
    last_at = None
    for job in recent:
        if (job.result or {}).get("status") != NETWORK_ERROR_STATE:
            break
        if last_at is None:
            last_at = job.completed_at
        count += 1
    return count, last_at


class JobScheduler:
    def __init__(self, worker_id: str | None = None, poll_interval: float = 2.0):
        self.worker_id = worker_id or f"worker-{os.getpid()}-{uuid4().hex[:6]}"
        self.poll_interval = poll_interval
        self._running = False

    def recover_stale_claims(self, db: Session) -> int:
        """
        Recovers jobs claimed by crashed workers where claimed_at is older than lease timeout.
        Resets them to PENDING so another worker can claim them.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=STALE_CLAIM_TIMEOUT_MINUTES)
        stale_jobs = (
            db.query(ScheduledJob)
            .filter(
                ScheduledJob.status == JobStatus.RUNNING,
                ScheduledJob.claimed_at < cutoff,
            )
            .all()
        )
        for job in stale_jobs:
            logger.warning(
                "Recovering stale job %s (claimed by %s at %s)",
                job.id,
                job.claimed_by,
                job.claimed_at,
            )
            job.status = JobStatus.PENDING
            job.claimed_by = None
            job.claimed_at = None
        if stale_jobs:
            db.commit()
        return len(stale_jobs)

    def enqueue_due_discovery_jobs(self, db: Session) -> int:
        """
        Inspects all enabled ContentStrategies. If a strategy is due and has no PENDING/RUNNING job,
        enqueues a new DISCOVERY job.
        """
        strategies = db.query(ContentStrategy).filter(ContentStrategy.enabled.is_(True)).all()
        enqueued_count = 0
        now = datetime.now(timezone.utc)

        for strat in strategies:
            # Check last completed discovery run
            last_job = (
                db.query(ScheduledJob)
                .filter(
                    ScheduledJob.job_type == JobType.DISCOVERY,
                    ScheduledJob.strategy_id == strat.id,
                    ScheduledJob.status == JobStatus.COMPLETED,
                )
                .order_by(ScheduledJob.completed_at.desc())
                .first()
            )
            last_run_time = last_job.completed_at if last_job else None

            if not is_strategy_discovery_due(strat, last_run_time, now=now):
                continue

            # Check if there is already an active (PENDING or RUNNING) job
            active_job = (
                db.query(ScheduledJob)
                .filter(
                    ScheduledJob.job_type == JobType.DISCOVERY,
                    ScheduledJob.strategy_id == strat.id,
                    ScheduledJob.status.in_([JobStatus.PENDING, JobStatus.RUNNING]),
                )
                .first()
            )
            if active_job:
                continue

            new_job = ScheduledJob(
                id=uuid4(),
                job_type=JobType.DISCOVERY,
                status=JobStatus.PENDING,
                strategy_id=strat.id,
                scheduled_at=now,
                payload={"skip_llm_if_no_new_items": True},
            )
            db.add(new_job)
            enqueued_count += 1

        if enqueued_count > 0:
            db.commit()
            logger.info("Enqueued %d due discovery jobs", enqueued_count)
        return enqueued_count

    def enqueue_due_analytics_sync_jobs(self, db: Session) -> int:
        """
        Inspects real PUBLISHED publications and schedules next backoff analytics sync attempt.
        """
        pubs = (
            db.query(Publication)
            .filter(
                Publication.status == PublicationStatus.PUBLISHED,
                Publication.external_id != None,
            )
            .all()
        )
        enqueued_count = 0
        now = datetime.now(timezone.utc)

        for pub in pubs:
            # How many previous completed or failed sync attempts exist on the ladder?
            sync_attempts = (
                db.query(ScheduledJob)
                .filter(
                    ScheduledJob.job_type == JobType.ANALYTICS_SYNC,
                    ScheduledJob.publication_id == pub.id,
                    ScheduledJob.status.in_([JobStatus.COMPLETED, JobStatus.FAILED]),
                    _counts_as_ladder_attempt(),
                )
                .count()
            )

            # Check if there is already an active job
            active_job = (
                db.query(ScheduledJob)
                .filter(
                    ScheduledJob.job_type == JobType.ANALYTICS_SYNC,
                    ScheduledJob.publication_id == pub.id,
                    ScheduledJob.status.in_([JobStatus.PENDING, JobStatus.RUNNING]),
                )
                .first()
            )
            if active_job:
                continue

            last_job = (
                db.query(ScheduledJob)
                .filter(
                    ScheduledJob.job_type == JobType.ANALYTICS_SYNC,
                    ScheduledJob.publication_id == pub.id,
                    ScheduledJob.status == JobStatus.COMPLETED,
                )
                .order_by(ScheduledJob.completed_at.desc())
                .first()
            )
            last_attempt_time = last_job.completed_at if last_job else None

            next_due = get_next_analytics_sync_time(
                pub,
                sync_attempts,
                last_attempt_time=last_attempt_time,
            )
            if not next_due:
                continue

            if now >= next_due:
                net_failures, last_net_at = consecutive_network_failures(db, pub.id)
                if net_failures >= NETWORK_RETRY_LIMIT:
                    # Paused after repeated network failures; surfaced in the schedule info.
                    continue
                if last_net_at is not None and now - last_net_at < NETWORK_RETRY_DELAY:
                    # Network retry cooldown. Does not advance the ladder.
                    continue

                new_job = ScheduledJob(
                    id=uuid4(),
                    job_type=JobType.ANALYTICS_SYNC,
                    status=JobStatus.PENDING,
                    publication_id=pub.id,
                    scheduled_at=next_due,
                    payload={"attempt": sync_attempts + 1},
                )
                db.add(new_job)
                enqueued_count += 1

        if enqueued_count > 0:
            db.commit()
            logger.info("Enqueued %d due analytics sync jobs", enqueued_count)
        return enqueued_count

    def claim_next_job(self, db: Session) -> ScheduledJob | None:
        """
        Atomically claims the next PENDING job using SELECT ... FOR UPDATE SKIP LOCKED.
        Guarantees that across multiple processes, exactly one worker claims any job.
        """
        now = datetime.now(timezone.utc)
        stmt = (
            select(ScheduledJob)
            .where(
                ScheduledJob.status == JobStatus.PENDING,
                ScheduledJob.scheduled_at <= now,
            )
            .order_by(ScheduledJob.scheduled_at.asc())
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        job = db.execute(stmt).scalars().first()
        if not job:
            return None

        job.status = JobStatus.RUNNING
        job.claimed_at = now
        job.claimed_by = self.worker_id
        db.commit()
        db.refresh(job)
        return job

    def execute_job(self, db: Session, job: ScheduledJob) -> bool:
        """
        Executes a claimed job and records result or error.
        """
        logger.info(
            "Worker %s executing job %s (type=%s, target_strat=%s, target_pub=%s)",
            self.worker_id,
            job.id,
            job.job_type.value,
            job.strategy_id,
            job.publication_id,
        )

        try:
          with LeaseKeeper(job.id, self.worker_id):
            if job.job_type == JobType.WORKFLOW_RUN:
                job.result = self._run_workflow_job(job.payload)
                job.status = JobStatus.COMPLETED

            elif job.job_type == JobType.DISCOVERY:
                skip_llm = job.payload.get("skip_llm_if_no_new_items", True)
                result = run_strategy_discovery(
                    db,
                    job.strategy_id,
                    skip_llm_if_no_new_items=skip_llm,
                )
                job.result = {
                    "sources_synced": result.get("sources_synced", 0),
                    "items_fetched": result.get("items_fetched", 0),
                    "new_items_count": result.get("new_items_count", 0),
                    "ideas_created_count": result.get("ideas_created_count", 0),
                    "created_idea_ids": [str(i) for i in result.get("created_idea_ids", [])],
                }
                job.status = JobStatus.COMPLETED

            elif job.job_type == JobType.ANALYTICS_SYNC:
                try:
                    snapshot = sync_publication_metrics(db, job.publication_id)
                    job.result = {
                        "snapshot_id": str(snapshot.id),
                        "collected_at": snapshot.collected_at.isoformat(),
                        "metrics": snapshot.metrics,
                        "status": "ready",
                    }
                    job.status = JobStatus.COMPLETED
                except HTTPException as http_exc:
                    if http_exc.status_code == 409:
                        # Metrics not yet available is a normal outcome per spec:
                        # "A 'not yet available' result is a normal outcome that schedules the next attempt;
                        # it is not an error and writes no snapshot."
                        job.result = {
                            "status": "not_ready",
                            "detail": str(http_exc.detail),
                        }
                        job.status = JobStatus.COMPLETED
                    elif isinstance(http_exc.detail, dict) and http_exc.detail.get("state") == NETWORK_ERROR_STATE:
                        # Recorded as FAILED so it is visible, but excluded from the ladder count.
                        job.result = {
                            "status": NETWORK_ERROR_STATE,
                            "detail": http_exc.detail.get("message"),
                        }
                        job.status = JobStatus.FAILED
                        job.error = f"{NETWORK_ERROR_STATE}: {http_exc.detail.get('technical')}"
                        job.completed_at = datetime.now(timezone.utc)
                        db.commit()
                        logger.warning(
                            "Worker %s: analytics sync for job %s could not reach the provider; retry scheduled",
                            self.worker_id,
                            job.id,
                        )
                        return False
                    else:
                        raise

            job.completed_at = datetime.now(timezone.utc)
            job.error = None
            db.commit()
            logger.info("Worker %s successfully completed job %s", self.worker_id, job.id)
            return True

        except Exception as exc:
            db.rollback()
            logger.error("Worker %s job %s failed: %s", self.worker_id, job.id, exc, exc_info=True)
            # Re-fetch job to update status
            job = db.query(ScheduledJob).filter(ScheduledJob.id == job.id).first()
            if job:
                job.status = JobStatus.FAILED
                job.completed_at = datetime.now(timezone.utc)
                job.error = f"{type(exc).__name__}: {str(exc)}"
                db.commit()
            return False

    def _run_workflow_job(self, payload: dict) -> dict:
        """
        Runs a graph start or resume. Start claims PENDING -> RUNNING atomically first;
        a job whose run is no longer PENDING is a duplicate and does nothing.
        """
        from uuid import UUID
        from app.graph.content_graph import (
            run_workflow_graph_background,
            resume_workflow_graph_background,
        )
        from app.workflows.models import WorkflowRun

        run_id = UUID(payload["workflow_run_id"])
        action = payload["action"]

        if action == "start":
            db = SessionLocal()
            try:
                row = db.query(WorkflowRun).filter(WorkflowRun.id == run_id).first()
                if row is None:
                    return {"status": "skipped", "reason": "workflow run not found"}
                strategy_id, idea_id = str(row.strategy_id), str(row.idea_id)
                claimed = claim_run_start(db, run_id)
            finally:
                db.close()
            if not claimed:
                return {"status": "skipped", "reason": "run is not PENDING (already started)"}
            run_workflow_graph_background(str(run_id), strategy_id, idea_id)
            return {"status": "started", "workflow_run_id": str(run_id)}

        if action == "resume":
            resume_workflow_graph_background(str(run_id), payload.get("decision") or {})
            return {"status": "resumed", "workflow_run_id": str(run_id)}

        raise ValueError(f"Unknown workflow job action: {action}")

    def run_once(self) -> int:
        """Performs one scheduler tick."""
        db = SessionLocal()
        try:
            write_heartbeat(db, self.worker_id)
            from app.settings_security.service import apply_saved_keys
            apply_saved_keys(db)  # pick up keys changed in the Settings page
            self.recover_stale_claims(db)
            self.enqueue_due_discovery_jobs(db)
            self.enqueue_due_analytics_sync_jobs(db)

            processed = 0
            while True:
                # Refresh between jobs so one long job does not look like a dead worker.
                write_heartbeat(db, self.worker_id)
                job = self.claim_next_job(db)
                if not job:
                    break
                self.execute_job(db, job)
                processed += 1
            return processed
        finally:
            db.close()

    def start(self):
        """Main loop for standalone worker."""
        logger.info("Starting scheduler worker %s...", self.worker_id)
        self._running = True
        while self._running:
            try:
                self.run_once()
            except Exception as e:
                logger.error("Error in scheduler loop: %s", e, exc_info=True)
            time.sleep(self.poll_interval)

    def stop(self):
        self._running = False


def get_strategy_discovery_schedule_info(db: Session, strategy: ContentStrategy) -> dict[str, Any]:
    """Returns discovery schedule status, interval, and last run details for a strategy."""
    interval = (strategy.config or {}).get("discovery_interval_hours")
    last_completed = (
        db.query(ScheduledJob)
        .filter(
            ScheduledJob.job_type == JobType.DISCOVERY,
            ScheduledJob.strategy_id == strategy.id,
            ScheduledJob.status == JobStatus.COMPLETED,
        )
        .order_by(ScheduledJob.completed_at.desc())
        .first()
    )
    last_run_info = None
    if last_completed:
        last_run_info = {
            "completed_at": last_completed.completed_at.isoformat() if last_completed.completed_at else None,
            "status": last_completed.status.value,
            "items_found": last_completed.result.get("items_fetched", 0) if last_completed.result else 0,
            "ideas_created": last_completed.result.get("ideas_created_count", 0) if last_completed.result else 0,
        }
    return {
        "interval_hours": float(interval) if interval is not None else None,
        "is_scheduled": interval is not None and float(interval) > 0 and strategy.enabled,
        "last_run": last_run_info,
    }


def get_publication_sync_schedule_info(db: Session, publication: Publication) -> dict[str, Any]:
    """
    Analytics sync state for a publication, derived from the job table.
    Times are UTC ISO strings; the UI converts them to local time with a zone label.
    """
    now = datetime.now(timezone.utc)
    sync_jobs = db.query(ScheduledJob).filter(
        ScheduledJob.job_type == JobType.ANALYTICS_SYNC,
        ScheduledJob.publication_id == publication.id,
    )

    active_job = sync_jobs.filter(
        ScheduledJob.status.in_([JobStatus.PENDING, JobStatus.RUNNING]),
    ).order_by(ScheduledJob.scheduled_at.asc()).first()

    last_job = sync_jobs.filter(
        ScheduledJob.status == JobStatus.COMPLETED,
    ).order_by(ScheduledJob.completed_at.desc()).first()

    ladder_attempts = sync_jobs.filter(
        ScheduledJob.status.in_([JobStatus.COMPLETED, JobStatus.FAILED]),
        _counts_as_ladder_attempt(),
    ).count()

    last_finished = sync_jobs.filter(
        ScheduledJob.status.in_([JobStatus.COMPLETED, JobStatus.FAILED]),
    ).order_by(ScheduledJob.completed_at.desc().nulls_last()).first()

    # A "not_ready" or "ready" completed job means Buffer answered. Network failures do not.
    last_buffer_response = sync_jobs.filter(
        ScheduledJob.status == JobStatus.COMPLETED,
    ).order_by(ScheduledJob.completed_at.desc()).first()

    net_failures, last_net_at = consecutive_network_failures(db, publication.id)
    network_paused = net_failures >= NETWORK_RETRY_LIMIT

    last_attempt_time = last_job.completed_at if last_job else None
    if active_job:
        next_sync = active_job.scheduled_at
    elif network_paused:
        next_sync = None
    else:
        next_sync = get_next_analytics_sync_time(
            publication,
            ladder_attempts,
            last_attempt_time=last_attempt_time,
        )

    last_attempt_outcome = None
    if last_finished:
        result_status = (last_finished.result or {}).get("status")
        if result_status == NETWORK_ERROR_STATE:
            last_attempt_outcome = NETWORK_ERROR_STATE
        elif last_finished.status == JobStatus.FAILED:
            last_attempt_outcome = "failed"
        else:
            last_attempt_outcome = result_status or "ready"

    return {
        "last_synced_at": last_job.completed_at.isoformat() if (last_job and last_job.completed_at) else None,
        "next_sync_at": next_sync.isoformat() if next_sync else None,
        "next_sync_overdue": bool(next_sync and next_sync <= now),
        "sync_attempt_count": ladder_attempts,
        "attempt_number": ladder_attempts + 1,
        "last_attempt_at": last_finished.completed_at.isoformat() if (last_finished and last_finished.completed_at) else None,
        "last_attempt_outcome": last_attempt_outcome,
        "last_attempt_error": last_finished.error if last_finished else None,
        "last_buffer_response_at": (
            last_buffer_response.completed_at.isoformat()
            if (last_buffer_response and last_buffer_response.completed_at) else None
        ),
        "network_failures_in_row": net_failures,
        "network_retry_paused": network_paused,
        "last_network_error_at": last_net_at.isoformat() if last_net_at else None,
        "scheduler_running": scheduler_running(db, now=now),
    }
