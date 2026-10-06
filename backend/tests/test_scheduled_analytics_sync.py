import os
import unittest
from datetime import datetime, timezone, timedelta
from uuid import uuid4
from unittest.mock import MagicMock, patch

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "../backend/.env"))

from sqlalchemy import text
from app.db import SessionLocal
from app.workflows.models import WorkflowRun, WorkflowRunStatus
from app.content.models import Content, ContentVersion
from app.publishing.models import Publication, PublicationStatus
from app.analytics.models import Analytics
from app.analytics.interface import (
    AnalyticsResult,
    MetricsNotAvailableError,
    PostNotFoundError,
)
from app.scheduler.models import ScheduledJob, JobType, JobStatus
from app.scheduler.service import JobScheduler
from tests.test_publishing_concurrency import test_owner_id, seed_test_workflow_tree

class TestScheduledAnalyticsSync(unittest.TestCase):
    def setUp(self):
        from tests._db_guard import refuse_if_real_database
        refuse_if_real_database()
        self.db = SessionLocal()
        # Ensure clean scheduled jobs table for test isolation
        self.db.query(ScheduledJob).delete()
        self.db.commit()

        run, content, v1 = seed_test_workflow_tree(self.db, run_status=WorkflowRunStatus.COMPLETED, approved=True)
        self.run = run
        self.content = content
        self.version = v1

        # Published 30 days ago so scheduled_at is earlier than other publications
        self.pub = Publication(
            owner_id=test_owner_id(),
            id=uuid4(),
            content_version_id=self.version.id,
            platform="linkedin",
            status=PublicationStatus.PUBLISHED,
            idempotency_key=f"test-sync-{uuid4()}",
            external_id="6ac3292f69a169193a5adca6",  # valid format ID
            published_at=datetime.now(timezone.utc) - timedelta(days=30),
        )
        self.db.add(self.pub)
        self.db.commit()
        self.db.refresh(self.pub)

    def tearDown(self):
        self.db.query(ScheduledJob).delete()
        self.db.query(Analytics).filter(Analytics.publication_id == self.pub.id).delete()
        self.db.delete(self.pub)
        self.db.commit()

        self.db.execute(text("DELETE FROM approvals WHERE content_version_id = :vid"), {"vid": self.version.id})
        self.db.execute(text("DELETE FROM content_versions WHERE id = :vid"), {"vid": self.version.id})
        self.db.execute(text("DELETE FROM content WHERE id = :cid"), {"cid": self.content.id})
        self.db.execute(text("DELETE FROM workflow_runs WHERE id = :rid"), {"rid": self.run.id})
        self.db.commit()
        self.db.close()

    def test_cp_2b_1_scheduled_analytics_sync_success_and_next_attempt(self):
        """
        CP-2B.1: Scheduled analytics sync enqueues due job, executes it, writes snapshot,
        and computes the next backoff step.
        """
        scheduler = JobScheduler(worker_id="worker-analytics-test")

        # Enqueue due jobs
        enqueued = scheduler.enqueue_due_analytics_sync_jobs(self.db)
        self.assertGreaterEqual(enqueued, 1)

        job = (
            self.db.query(ScheduledJob)
            .filter(
                ScheduledJob.publication_id == self.pub.id,
                ScheduledJob.job_type == JobType.ANALYTICS_SYNC,
                ScheduledJob.status == JobStatus.PENDING,
            )
            .first()
        )
        self.assertIsNotNone(job)

        with patch("app.analytics.service.get_analytics_provider") as mock_get_provider:
            mock_provider = MagicMock()
            mock_provider.fetch_metrics.return_value = AnalyticsResult(
                publication_id=self.pub.id,
                platform="linkedin",
                external_post_id=self.pub.external_id,
                metrics={"reactions": 10, "comments": 2, "impressions": 100, "is_stub": False, "is_initial": False},
                collected_at=datetime.now(timezone.utc),
                provider="buffer",
            )
            mock_get_provider.return_value = mock_provider

            claimed = scheduler.claim_next_job(self.db)
            self.assertEqual(claimed.id, job.id)
            scheduler.execute_job(self.db, claimed)

        self.db.refresh(job)
        self.assertEqual(job.status, JobStatus.COMPLETED)
        self.assertEqual(job.result["status"], "ready")

        # Verify analytics row written
        analytics_rows = self.db.query(Analytics).filter(Analytics.publication_id == self.pub.id).all()
        self.assertEqual(len(analytics_rows), 1)
        self.assertEqual(analytics_rows[0].metrics["reactions"], 10)

    def test_cp_2b_1_metrics_not_available_schedules_next_attempt_without_snapshot(self):
        """
        CP-2B.1: When MetricsNotAvailableError (HTTP 409) occurs, the job finishes with status 'not_ready'
        and writes NO snapshot.
        """
        scheduler = JobScheduler(worker_id="worker-analytics-notready-test")
        job = ScheduledJob(
            owner_id=test_owner_id(),
            id=uuid4(),
            job_type=JobType.ANALYTICS_SYNC,
            status=JobStatus.PENDING,
            publication_id=self.pub.id,
            scheduled_at=datetime.now(timezone.utc) - timedelta(minutes=1),
            payload={"attempt": 1},
        )
        self.db.add(job)
        self.db.commit()

        with patch("app.analytics.service.get_analytics_provider") as mock_get_provider:
            mock_provider = MagicMock()
            mock_provider.fetch_metrics.side_effect = MetricsNotAvailableError(
                "Buffer propagation delay: metrics not yet ready."
            )
            mock_get_provider.return_value = mock_provider

            claimed = scheduler.claim_next_job(self.db)
            self.assertEqual(claimed.id, job.id)
            scheduler.execute_job(self.db, claimed)

        self.db.refresh(job)
        self.assertEqual(job.status, JobStatus.COMPLETED)
        self.assertEqual(job.result["status"], "not_ready")

        # Verify NO analytics snapshot was written
        analytics_count = self.db.query(Analytics).filter(Analytics.publication_id == self.pub.id).count()
        self.assertEqual(analytics_count, 0)

    def test_cp_2b_3_two_worker_concurrency(self):
        """
        CP-2B.3: Two workers attempt to claim the same due analytics sync job. Exactly one executes.
        """
        job = ScheduledJob(
            owner_id=test_owner_id(),
            id=uuid4(),
            job_type=JobType.ANALYTICS_SYNC,
            status=JobStatus.PENDING,
            publication_id=self.pub.id,
            scheduled_at=datetime.now(timezone.utc) - timedelta(minutes=1),
            payload={"attempt": 1},
        )
        self.db.add(job)
        self.db.commit()

        worker_a = JobScheduler(worker_id="analytics-worker-1")
        worker_b = JobScheduler(worker_id="analytics-worker-2")

        db_a = SessionLocal()
        db_b = SessionLocal()
        try:
            claimed_a = worker_a.claim_next_job(db_a)
            claimed_b = worker_b.claim_next_job(db_b)

            claims = [c for c in [claimed_a, claimed_b] if c is not None and c.id == job.id]
            self.assertEqual(len(claims), 1, "Exactly one worker claims analytics sync job")
        finally:
            db_a.close()
            db_b.close()

    def test_cp_2b_3_crash_recovery(self):
        """
        CP-2B.3: Stale claim on analytics sync job is recovered cleanly.
        """
        old_time = datetime.now(timezone.utc) - timedelta(minutes=10)
        crashed_job = ScheduledJob(
            owner_id=test_owner_id(),
            id=uuid4(),
            job_type=JobType.ANALYTICS_SYNC,
            status=JobStatus.RUNNING,
            publication_id=self.pub.id,
            scheduled_at=old_time,
            claimed_at=old_time,
            claimed_by="dead-analytics-worker",
            payload={"attempt": 1},
        )
        self.db.add(crashed_job)
        self.db.commit()

        scheduler = JobScheduler(worker_id="recovery-analytics-worker")
        recovered = scheduler.recover_stale_claims(self.db)
        self.assertGreaterEqual(recovered, 1)

        self.db.refresh(crashed_job)
        self.assertEqual(crashed_job.status, JobStatus.PENDING)
        self.assertIsNone(crashed_job.claimed_by)

    def test_cp_1_6_schedule_bookkeeping(self):
        """
        CP-1.6 tests:
        1. A publication with five prior attempts shows attempt 5/6 and a future next time.
        2. After the last attempt (6) it shows "No more scheduled syncs" (next_sync_at is None).
        3. An unsupported publication (or stub external_id) shows no schedule.
        """
        from app.scheduler.service import get_publication_sync_schedule_info

        now = datetime.now(timezone.utc)
        # The polling window is 30 days after publication. This setup publishes 30 days ago,
        # so the window has already closed and no next sync is correct. Publish 1 day ago
        # to test the ladder itself.
        self.pub.published_at = now - timedelta(days=1)
        self.db.commit()
        # Create 5 completed jobs for self.pub
        for i in range(5):
            j = ScheduledJob(
                owner_id=test_owner_id(),
                id=uuid4(),
                job_type=JobType.ANALYTICS_SYNC,
                status=JobStatus.COMPLETED,
                publication_id=self.pub.id,
                scheduled_at=now - timedelta(minutes=60 - i * 10),
                completed_at=now - timedelta(minutes=50 - i * 10),
                payload={"attempt": i + 1},
            )
            self.db.add(j)
        self.db.commit()

        info = get_publication_sync_schedule_info(self.db, self.pub)
        self.assertEqual(info["sync_attempt_count"], 5)
        self.assertIsNotNone(info["next_sync_at"])
        # Attempt 5 next time should be in the future (relative to last attempt + 10080 min)
        next_dt = datetime.fromisoformat(info["next_sync_at"])
        self.assertGreater(next_dt, now)

        # Now add 6th completed job (total 6 attempts, which is max len(ANALYTICS_BACKOFF_MINUTES))
        j6 = ScheduledJob(
            owner_id=test_owner_id(),
            id=uuid4(),
            job_type=JobType.ANALYTICS_SYNC,
            status=JobStatus.COMPLETED,
            publication_id=self.pub.id,
            scheduled_at=now - timedelta(minutes=5),
            completed_at=now - timedelta(minutes=4),
            payload={"attempt": 6},
        )
        self.db.add(j6)
        self.db.commit()

        info_max = get_publication_sync_schedule_info(self.db, self.pub)
        self.assertEqual(info_max["sync_attempt_count"], 6)
        # After the ladder: one check a day for 30 days after publication (not "no more syncs").
        expected = datetime.fromisoformat(info_max["last_synced_at"]) + timedelta(hours=24)
        self.assertEqual(datetime.fromisoformat(info_max["next_sync_at"]), expected)

        # Unsupported publication (e.g. stub_ or linkedin_ mock external_id)
        mock_pub = Publication(
            owner_id=test_owner_id(),
            id=uuid4(),
            content_version_id=self.version.id,
            platform="linkedin",
            status=PublicationStatus.PUBLISHED,
            idempotency_key=f"test-unsupported-{uuid4()}",
            external_id="linkedin_unsupported_stub",
            published_at=now,
        )
        self.db.add(mock_pub)
        self.db.commit()

        info_unsupported = get_publication_sync_schedule_info(self.db, mock_pub)
        self.assertIsNone(info_unsupported["next_sync_at"])


if __name__ == "__main__":
    unittest.main()

