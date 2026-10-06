import os
import unittest
from tests.test_publishing_concurrency import test_owner_id
from datetime import datetime, timezone, timedelta
from uuid import uuid4
from unittest.mock import patch

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "../backend/.env"))

from app.db import SessionLocal
from app.strategies.models import ContentStrategy
from app.sources.models import Source
from app.strategies.service import sync_strategy_source_links
from app.scheduler.models import ScheduledJob, JobType, JobStatus
from app.scheduler.service import JobScheduler
from app.ideas.models import Idea

class TestScheduledDiscoveryConcurrencyAndFailure(unittest.TestCase):
    def setUp(self):
        self.db = SessionLocal()
        os.environ["MIN_DISCOVERY_INTERVAL_HOURS"] = "0.0"

        src = self.db.query(Source).filter(Source.enabled.is_(True), Source.url != None).first()
        self.assertIsNotNone(src, "No active source found")
        self.src = src

        self.strat = ContentStrategy(
            owner_id=test_owner_id(),
            id=uuid4(),
            name=f"TEMP-schedule-conc-{uuid4().hex[:6]}",
            description="Throwaway strategy for CP-2A.3-5",
            config={
                "niche": "Distributed Systems Concurrency",
                "discovery_interval_hours": 0.001,
            },
            enabled=True,
        )
        self.db.add(self.strat)
        self.db.commit()
        sync_strategy_source_links(self.db, self.strat.id, [src.id])
        self.db.commit()

    def tearDown(self):
        self.db.query(ScheduledJob).filter(ScheduledJob.strategy_id == self.strat.id).delete()
        self.db.query(Idea).filter(Idea.strategy_id == self.strat.id).delete()
        self.db.delete(self.strat)
        self.db.commit()
        self.db.close()

    def test_cp_2a_3_no_double_execution_concurrency(self):
        """
        CP-2A.3: Start two scheduler workers against the same database with one due job.
        Verify exactly one claims and executes the job.
        """
        # Create one due PENDING job
        now = datetime.now(timezone.utc)
        job = ScheduledJob(
            owner_id=test_owner_id(),
            id=uuid4(),
            job_type=JobType.DISCOVERY,
            status=JobStatus.PENDING,
            strategy_id=self.strat.id,
            scheduled_at=now - timedelta(minutes=1),
            payload={"skip_llm_if_no_new_items": True},
        )
        self.db.add(job)
        self.db.commit()

        worker_a = JobScheduler(worker_id="worker-proc-alpha")
        worker_b = JobScheduler(worker_id="worker-proc-beta")

        # Two worker sessions attempt to claim
        db_a = SessionLocal()
        db_b = SessionLocal()
        try:
            claimed_a = worker_a.claim_next_job(db_a)
            claimed_b = worker_b.claim_next_job(db_b)

            # Exactly one worker claimed the job
            claims = [c for c in [claimed_a, claimed_b] if c is not None and c.id == job.id]
            self.assertEqual(len(claims), 1, "Exactly one worker should have claimed the job")

            winner_worker = worker_a if claimed_a else worker_b
            winner_db = db_a if claimed_a else db_b
            winner_job = claimed_a or claimed_b

            # Winner executes
            winner_worker.execute_job(winner_db, winner_job)

            # Job is COMPLETED exactly once in database
            self.db.refresh(job)
            self.assertEqual(job.status, JobStatus.COMPLETED)
            self.assertIn(job.claimed_by, ["worker-proc-alpha", "worker-proc-beta"])
        finally:
            db_a.close()
            db_b.close()

    def test_cp_2a_4_stale_claim_recovery_after_crash(self):
        """
        CP-2A.4: Simulate crash (kill -9) mid-run by leaving job RUNNING with old claimed_at.
        Verify recover_stale_claims recovers claim and job completes without duplication.
        """
        # Job claimed 10 minutes ago by dead worker
        crashed_time = datetime.now(timezone.utc) - timedelta(minutes=10)
        crashed_job = ScheduledJob(
            owner_id=test_owner_id(),
            id=uuid4(),
            job_type=JobType.DISCOVERY,
            status=JobStatus.RUNNING,
            strategy_id=self.strat.id,
            scheduled_at=crashed_time,
            claimed_at=crashed_time,
            claimed_by="crashed-worker-pid-99999",
            payload={"skip_llm_if_no_new_items": True},
        )
        self.db.add(crashed_job)
        self.db.commit()

        scheduler = JobScheduler(worker_id="recovery-worker-live")
        recovered_count = scheduler.recover_stale_claims(self.db)
        self.assertGreaterEqual(recovered_count, 1)

        self.db.refresh(crashed_job)
        self.assertEqual(crashed_job.status, JobStatus.PENDING)
        self.assertIsNone(crashed_job.claimed_by)

        # Now worker claims and executes it cleanly
        claimed = scheduler.claim_next_job(self.db)
        self.assertIsNotNone(claimed)
        self.assertEqual(claimed.id, crashed_job.id)
        self.assertEqual(claimed.claimed_by, "recovery-worker-live")

        scheduler.execute_job(self.db, claimed)
        self.db.refresh(crashed_job)
        self.assertEqual(crashed_job.status, JobStatus.COMPLETED)

    @patch("app.strategies.service.fetch_rss_items")
    def test_cp_2a_5_failure_behavior_unreachable_feed(self, mock_rss):
        """
        CP-2A.5: Simulate unreachable feed.
        Verify failure recorded with classification, status=FAILED, error populated.
        """
        mock_rss.side_effect = ConnectionError("Feed unreachable: Connection timed out")

        job = ScheduledJob(
            owner_id=test_owner_id(),
            id=uuid4(),
            job_type=JobType.DISCOVERY,
            status=JobStatus.PENDING,
            strategy_id=self.strat.id,
            scheduled_at=datetime.now(timezone.utc) - timedelta(minutes=1),
            payload={"skip_llm_if_no_new_items": False},
        )
        self.db.add(job)
        self.db.commit()

        scheduler = JobScheduler(worker_id="worker-fail-test")
        claimed = scheduler.claim_next_job(self.db)
        self.assertIsNotNone(claimed)

        success = scheduler.execute_job(self.db, claimed)
        self.assertFalse(success)

        self.db.refresh(job)
        self.assertEqual(job.status, JobStatus.FAILED)
        self.assertIsNotNone(job.error)
        self.assertIn("ConnectionError", job.error)
        self.assertIn("Feed unreachable", job.error)

    @patch("app.strategies.service.execute_scout_and_score")
    @patch("app.strategies.service.fetch_rss_items")
    def test_cp_2a_5_failure_behavior_openrouter_rate_limit(self, mock_rss, mock_llm):
        """
        CP-2A.5: Simulate OpenRouter 429 rate-limit error.
        Verify failure recorded with classification.
        """
        mock_rss.return_value = [
            {
                "external_id": f"test-item-{uuid4().hex[:8]}",
                "content_hash": "hash123",
                "title": "New Distributed Systems Paper",
                "url": "https://example.com/paper",
                "description": "Novel replication consensus algorithm",
            }
        ]
        mock_llm.side_effect = RuntimeError("OpenRouter API error (HTTP 429): Rate limit reached. Window 60s.")

        job = ScheduledJob(
            owner_id=test_owner_id(),
            id=uuid4(),
            job_type=JobType.DISCOVERY,
            status=JobStatus.PENDING,
            strategy_id=self.strat.id,
            scheduled_at=datetime.now(timezone.utc) - timedelta(minutes=1),
            payload={"skip_llm_if_no_new_items": False},
        )
        self.db.add(job)
        self.db.commit()

        scheduler = JobScheduler(worker_id="worker-ratelimit-test")
        claimed = scheduler.claim_next_job(self.db)
        self.assertIsNotNone(claimed)

        success = scheduler.execute_job(self.db, claimed)
        self.assertFalse(success)

        self.db.refresh(job)
        self.assertEqual(job.status, JobStatus.FAILED)
        self.assertIsNotNone(job.error)
        self.assertIn("RuntimeError", job.error)
        self.assertIn("HTTP 429", job.error)

if __name__ == "__main__":
    unittest.main()
