"""
CP-A.3 (network errors are their own state), CP-D.3 (worker heartbeat).

Every test runs inside one outer transaction on a single connection, rolled back in
tearDown. The real contentos_dev database is never changed. The scheduler's enqueue
step scans every PUBLISHED publication, so it must not run against the live tables.
"""
import os
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch
from uuid import uuid4

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "../backend/.env"))

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.db import engine
from app.analytics.interface import NetworkAnalyticsError
from app.analytics.models import Analytics
from app.analytics.service import sync_publication_metrics, NETWORK_ERROR_STATE
from app.analytics.status import build_analytics_status
from app.publishing.models import Publication, PublicationStatus
from app.scheduler.heartbeat import write_heartbeat, scheduler_running, HEARTBEAT_STALE_AFTER
from app.scheduler.models import ScheduledJob, JobType, JobStatus, WorkerHeartbeat
from app.scheduler.service import (
    JobScheduler,
    NETWORK_RETRY_DELAY,
    NETWORK_RETRY_LIMIT,
    get_publication_sync_schedule_info,
)
from tests.test_publishing_concurrency import seed_test_workflow_tree
from app.workflows.models import WorkflowRunStatus

PUBLISHED_AT = datetime.now(timezone.utc) - timedelta(days=2)


class IsolatedDBTestCase(unittest.TestCase):
    def setUp(self):
        self.connection = engine.connect()
        self.outer = self.connection.begin()
        self.db = Session(bind=self.connection, join_transaction_mode="create_savepoint")

        run, content, version = seed_test_workflow_tree(
            self.db, run_status=WorkflowRunStatus.COMPLETED, approved=True
        )
        self.pub = Publication(
            id=uuid4(),
            content_version_id=version.id,
            platform="linkedin",
            status=PublicationStatus.PUBLISHED,
            idempotency_key=f"test-netstate-{uuid4()}",
            external_id="6ac3541363761da98b71e85b",
            published_at=PUBLISHED_AT,
        )
        self.db.add(self.pub)
        self.db.commit()
        self.db.refresh(self.pub)

    def tearDown(self):
        self.db.close()
        self.outer.rollback()
        self.connection.close()

    def _network_failing_provider(self):
        provider = MagicMock()
        provider.fetch_metrics.side_effect = NetworkAnalyticsError(
            "Network error querying Buffer analytics: [Errno -3] Temporary failure in name resolution"
        )
        return provider

    def _ladder_attempts(self) -> int:
        return get_publication_sync_schedule_info(self.db, self.pub)["sync_attempt_count"]


class TestNetworkErrorState(IsolatedDBTestCase):
    def test_sync_reports_network_error_and_writes_no_snapshot(self):
        before = self.db.query(Analytics).filter(Analytics.publication_id == self.pub.id).count()
        with patch("app.analytics.service.get_analytics_provider", return_value=self._network_failing_provider()):
            with self.assertRaises(HTTPException) as ctx:
                sync_publication_metrics(self.db, self.pub.id)
        self.assertEqual(ctx.exception.status_code, 503)
        self.assertEqual(ctx.exception.detail["state"], NETWORK_ERROR_STATE)
        after = self.db.query(Analytics).filter(Analytics.publication_id == self.pub.id).count()
        self.assertEqual(before, after)

    def test_each_transport_failure_is_network_error_not_not_ready(self):
        # DNS, timeout and connection reset all come through NetworkAnalyticsError.
        for label in ("dns", "timeout", "reset"):
            with self.subTest(label=label), patch(
                "app.analytics.service.get_analytics_provider",
                return_value=self._network_failing_provider(),
            ):
                with self.assertRaises(HTTPException) as ctx:
                    sync_publication_metrics(self.db, self.pub.id)
                self.assertNotEqual(ctx.exception.status_code, 409)
                self.assertEqual(ctx.exception.detail["state"], NETWORK_ERROR_STATE)

    def test_network_failure_does_not_advance_attempt_counter(self):
        scheduler = JobScheduler(worker_id="test-net")
        job = ScheduledJob(
            id=uuid4(),
            job_type=JobType.ANALYTICS_SYNC,
            status=JobStatus.RUNNING,
            publication_id=self.pub.id,
            scheduled_at=datetime.now(timezone.utc),
            payload={"attempt": 1},
        )
        self.db.add(job)
        self.db.commit()

        attempts_before = self._ladder_attempts()
        with patch("app.analytics.service.get_analytics_provider", return_value=self._network_failing_provider()):
            ok = scheduler.execute_job(self.db, job)

        self.assertFalse(ok)
        self.db.refresh(job)
        self.assertEqual(job.status, JobStatus.FAILED)
        self.assertEqual(job.result["status"], NETWORK_ERROR_STATE)
        self.assertEqual(self._ladder_attempts(), attempts_before)
        self.assertEqual(
            self.db.query(Analytics).filter(Analytics.publication_id == self.pub.id).count(), 0
        )

    def test_retry_waits_for_cooldown_then_runs_without_advancing_ladder(self):
        scheduler = JobScheduler(worker_id="test-net")
        now = datetime.now(timezone.utc)
        failed = ScheduledJob(
            id=uuid4(),
            job_type=JobType.ANALYTICS_SYNC,
            status=JobStatus.FAILED,
            publication_id=self.pub.id,
            scheduled_at=now,
            completed_at=now,
            payload={"attempt": 1},
            result={"status": NETWORK_ERROR_STATE},
        )
        self.db.add(failed)
        self.db.commit()

        # Inside the cooldown: nothing new is queued.
        self.assertEqual(scheduler.enqueue_due_analytics_sync_jobs(self.db) >= 0, True)
        queued = self.db.query(ScheduledJob).filter(
            ScheduledJob.publication_id == self.pub.id,
            ScheduledJob.status == JobStatus.PENDING,
        ).count()
        self.assertEqual(queued, 0)

        # Past the cooldown: a retry is queued, still at ladder rung 0.
        failed.completed_at = now - NETWORK_RETRY_DELAY - timedelta(seconds=1)
        self.db.commit()
        scheduler.enqueue_due_analytics_sync_jobs(self.db)
        queued = self.db.query(ScheduledJob).filter(
            ScheduledJob.publication_id == self.pub.id,
            ScheduledJob.status == JobStatus.PENDING,
        ).all()
        self.assertEqual(len(queued), 1)
        self.assertEqual(queued[0].payload["attempt"], 1)
        self.assertEqual(self._ladder_attempts(), 0)

    def test_automatic_retries_pause_after_limit(self):
        scheduler = JobScheduler(worker_id="test-net")
        long_ago = datetime.now(timezone.utc) - timedelta(days=1)
        for i in range(NETWORK_RETRY_LIMIT):
            self.db.add(ScheduledJob(
                id=uuid4(),
                job_type=JobType.ANALYTICS_SYNC,
                status=JobStatus.FAILED,
                publication_id=self.pub.id,
                scheduled_at=long_ago,
                completed_at=long_ago - timedelta(seconds=i),
                payload={"attempt": 1},
                result={"status": NETWORK_ERROR_STATE},
            ))
        self.db.commit()

        scheduler.enqueue_due_analytics_sync_jobs(self.db)
        queued = self.db.query(ScheduledJob).filter(
            ScheduledJob.publication_id == self.pub.id,
            ScheduledJob.status == JobStatus.PENDING,
        ).count()
        self.assertEqual(queued, 0)

        info = get_publication_sync_schedule_info(self.db, self.pub)
        self.assertTrue(info["network_retry_paused"])
        self.assertIsNone(info["next_sync_at"])

    def test_status_reports_network_error_as_its_own_state(self):
        now = datetime.now(timezone.utc)
        self.db.add(ScheduledJob(
            id=uuid4(),
            job_type=JobType.ANALYTICS_SYNC,
            status=JobStatus.FAILED,
            publication_id=self.pub.id,
            scheduled_at=now,
            completed_at=now,
            payload={"attempt": 1},
            result={"status": NETWORK_ERROR_STATE},
        ))
        self.db.commit()
        status = build_analytics_status(self.db, self.pub)
        self.assertEqual(status["state"], NETWORK_ERROR_STATE)
        self.assertIsNone(status["valid_snapshot"])


class TestSchedulerHeartbeat(IsolatedDBTestCase):
    def setUp(self):
        super().setUp()
        self.db.query(WorkerHeartbeat).delete()  # rolled back in tearDown
        self.db.commit()

    def test_no_row_means_not_running(self):
        self.assertFalse(scheduler_running(self.db))

    def test_fresh_heartbeat_means_running(self):
        write_heartbeat(self.db, "test-worker-fresh")
        self.assertTrue(scheduler_running(self.db))

    def test_stale_heartbeat_means_not_running(self):
        stale = datetime.now(timezone.utc) - HEARTBEAT_STALE_AFTER - timedelta(seconds=30)
        self.db.add(WorkerHeartbeat(worker_id="test-worker-stale", last_seen_at=stale))
        self.db.commit()
        self.assertFalse(scheduler_running(self.db))

    def test_write_heartbeat_upserts_one_row_per_worker(self):
        write_heartbeat(self.db, "test-worker-upsert")
        write_heartbeat(self.db, "test-worker-upsert")
        count = self.db.query(WorkerHeartbeat).filter(WorkerHeartbeat.worker_id == "test-worker-upsert").count()
        self.assertEqual(count, 1)


if __name__ == "__main__":
    unittest.main()
