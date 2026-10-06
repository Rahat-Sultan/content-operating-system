"""
Keeps a long-running job's claim alive and the worker's heartbeat fresh.

A production graph run can take many minutes (LLM calls). Without renewal the
claim would look stale after STALE_CLAIM_TIMEOUT_MINUTES and another worker
would run the job a second time, and the UI would show the worker as stopped.
"""
import logging
import threading
from datetime import datetime, timezone
from uuid import UUID

from app.db import SessionLocal
from app.scheduler.heartbeat import write_heartbeat
from app.scheduler.models import ScheduledJob, JobStatus

logger = logging.getLogger("scheduler")

LEASE_RENEW_SECONDS = 30.0


class LeaseKeeper:
    def __init__(
        self,
        job_id: UUID,
        worker_id: str,
        interval: float = LEASE_RENEW_SECONDS,
        session_factory=SessionLocal,
    ):
        self.job_id = job_id
        self.worker_id = worker_id
        self.interval = interval
        self.session_factory = session_factory
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name=f"lease-{job_id}", daemon=True)

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, *exc):
        self._stop.set()
        self._thread.join(timeout=self.interval + 5)

    def renew_once(self) -> None:
        db = self.session_factory()
        try:
            db.query(ScheduledJob).filter(
                ScheduledJob.id == self.job_id,
                ScheduledJob.status == JobStatus.RUNNING,
                ScheduledJob.claimed_by == self.worker_id,
            ).update(
                {ScheduledJob.claimed_at: datetime.now(timezone.utc)},
                synchronize_session=False,
            )
            db.commit()
            write_heartbeat(db, self.worker_id)
        finally:
            db.close()

    def _run(self) -> None:
        while not self._stop.wait(self.interval):
            try:
                self.renew_once()
            except Exception as exc:  # the job itself keeps running; the next renewal retries
                logger.warning("Lease renewal failed for job %s: %s", self.job_id, exc)
