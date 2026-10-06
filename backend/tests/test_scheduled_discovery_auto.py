import os
import unittest
from tests.test_publishing_concurrency import test_owner_id
from datetime import datetime, timezone, timedelta
from uuid import uuid4

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "../backend/.env"))

from app.db import SessionLocal
from app.strategies.models import ContentStrategy
from app.sources.models import Source
from app.scheduler.models import ScheduledJob, JobType, JobStatus
from app.scheduler.service import JobScheduler
from app.ideas.models import Idea
from app.sources.models import SourceItem

class TestScheduledDiscoveryAutomatic(unittest.TestCase):
    def setUp(self):
        self.db = SessionLocal()
        # Set MIN_DISCOVERY_INTERVAL_HOURS to 0 for test
        os.environ["MIN_DISCOVERY_INTERVAL_HOURS"] = "0.0"

        # Attach real active source
        src = self.db.query(Source).filter(Source.enabled.is_(True), Source.url != None).first()
        self.assertIsNotNone(src, "No active source found")

        self.strat = ContentStrategy(
            owner_id=test_owner_id(),
            id=uuid4(),
            name=f"TEMP-schedule-test-{uuid4().hex[:6]}",
            description="Throwaway strategy for CP-2A.2",
            config={
                "niche": "Distributed Systems",
                "discovery_interval_hours": 0.001,  # immediate
            },
            enabled=True,
        )
        self.db.add(self.strat)
        self.db.commit()
        self.db.refresh(self.strat)

        from app.strategies.service import sync_strategy_source_links
        sync_strategy_source_links(self.db, self.strat.id, [src.id])
        self.db.commit()

    def tearDown(self):
        # Clean up jobs and throwaway strategy
        self.db.query(ScheduledJob).filter(ScheduledJob.strategy_id == self.strat.id).delete()
        self.db.query(Idea).filter(Idea.strategy_id == self.strat.id).delete()
        self.db.delete(self.strat)
        self.db.commit()
        self.db.close()

    def test_real_automatic_discovery_run(self):
        scheduler = JobScheduler(worker_id="test-worker-automatic")
        # Run one tick of the scheduler
        processed = scheduler.run_once()
        self.assertGreaterEqual(processed, 1, "Scheduler should have claimed and processed due job")

        # Verify job recorded in DB
        job = (
            self.db.query(ScheduledJob)
            .filter(
                ScheduledJob.strategy_id == self.strat.id,
                ScheduledJob.job_type == JobType.DISCOVERY,
            )
            .first()
        )
        self.assertIsNotNone(job)
        self.assertEqual(job.status, JobStatus.COMPLETED)
        self.assertIsNotNone(job.completed_at)
        self.assertIsNotNone(job.result)
        self.assertGreaterEqual(job.result["sources_synced"], 1)

if __name__ == "__main__":
    unittest.main()
