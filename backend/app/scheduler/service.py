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
from app.analytics.service import sync_publication_metrics

logger = logging.getLogger("scheduler")

# Stale claim lease timeout: 5 minutes
STALE_CLAIM_TIMEOUT_MINUTES = 5


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
            # How many previous completed or failed sync attempts exist?
            sync_attempts = (
                db.query(ScheduledJob)
                .filter(
                    ScheduledJob.job_type == JobType.ANALYTICS_SYNC,
                    ScheduledJob.publication_id == pub.id,
                    ScheduledJob.status.in_([JobStatus.COMPLETED, JobStatus.FAILED]),
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
            if job.job_type == JobType.DISCOVERY:
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

    def run_once(self) -> int:
        """Performs one scheduler tick."""
        db = SessionLocal()
        try:
            self.recover_stale_claims(db)
            self.enqueue_due_discovery_jobs(db)
            self.enqueue_due_analytics_sync_jobs(db)

            processed = 0
            while True:
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
    """Returns analytics sync history and next scheduled sync details for a publication."""
    # Check for active scheduled job
    active_job = (
        db.query(ScheduledJob)
        .filter(
            ScheduledJob.job_type == JobType.ANALYTICS_SYNC,
            ScheduledJob.publication_id == publication.id,
            ScheduledJob.status.in_([JobStatus.PENDING, JobStatus.RUNNING]),
        )
        .first()
    )

    last_job = (
        db.query(ScheduledJob)
        .filter(
            ScheduledJob.job_type == JobType.ANALYTICS_SYNC,
            ScheduledJob.publication_id == publication.id,
            ScheduledJob.status == JobStatus.COMPLETED,
        )
        .order_by(ScheduledJob.completed_at.desc())
        .first()
    )
    completed_or_failed_count = (
        db.query(ScheduledJob)
        .filter(
            ScheduledJob.job_type == JobType.ANALYTICS_SYNC,
            ScheduledJob.publication_id == publication.id,
            ScheduledJob.status.in_([JobStatus.COMPLETED, JobStatus.FAILED]),
        )
        .count()
    )

    last_attempt_time = last_job.completed_at if last_job else None
    if active_job:
        next_sync = active_job.scheduled_at
    else:
        next_sync = get_next_analytics_sync_time(
            publication,
            completed_or_failed_count,
            last_attempt_time=last_attempt_time,
        )

    return {
        "last_synced_at": last_job.completed_at.isoformat() if (last_job and last_job.completed_at) else None,
        "next_sync_at": next_sync.isoformat() if next_sync else None,
        "sync_attempt_count": completed_or_failed_count,
    }


