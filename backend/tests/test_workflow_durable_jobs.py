"""
Durable production workflow jobs: start and resume are queued atomically and run by
the scheduler worker, with duplicate starts and lost leases handled.

Every test runs in one outer transaction on a single connection, rolled back in
tearDown. The real contentos_dev database is never changed.
"""
import os
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from uuid import uuid4

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "../backend/.env"))

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db import engine
from app.scheduler.lease import LeaseKeeper
from app.scheduler.models import ScheduledJob, JobType, JobStatus
from app.scheduler.service import JobScheduler
from app.scheduler.workflow_jobs import claim_run_start, enqueue_workflow_job
from app.workflows.models import WorkflowRun, WorkflowRunStatus
from app.workflows.service import create_workflow_run
from tests.test_publishing_concurrency import test_owner_id, seed_test_workflow_tree


class IsolatedDB(unittest.TestCase):
    def setUp(self):
        self.connection = engine.connect()
        self.outer = self.connection.begin()
        self.db = Session(bind=self.connection, join_transaction_mode="create_savepoint")
        self.run, self.content, self.version = seed_test_workflow_tree(
            self.db, run_status=WorkflowRunStatus.COMPLETED, approved=True
        )

    def tearDown(self):
        self.db.close()
        self.outer.rollback()
        self.connection.close()

    def session_factory(self):
        return Session(bind=self.connection, join_transaction_mode="create_savepoint")

    def workflow_jobs(self, run_id):
        return self.db.query(ScheduledJob).filter(
            ScheduledJob.job_type == JobType.WORKFLOW_RUN,
            ScheduledJob.payload["workflow_run_id"].astext == str(run_id),
        ).all()


class TestAtomicQueueing(IsolatedDB):
    def test_start_queues_run_and_job_together_as_pending(self):
        # The seeded run on this idea is COMPLETED, so a new run is allowed.
        created = create_workflow_run(self.db, self.run.strategy_id, self.run.idea_id, owner_id=test_owner_id())
        self.assertEqual(created.status, WorkflowRunStatus.PENDING)
        jobs = self.workflow_jobs(created.id)
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].status, JobStatus.PENDING)
        self.assertEqual(jobs[0].payload["action"], "start")

    def test_second_start_for_active_idea_is_rejected_and_queues_nothing(self):
        first = create_workflow_run(self.db, self.run.strategy_id, self.run.idea_id, owner_id=test_owner_id())
        before = self.db.query(ScheduledJob).filter(ScheduledJob.job_type == JobType.WORKFLOW_RUN).count()
        with self.assertRaises(HTTPException) as ctx:
            create_workflow_run(self.db, self.run.strategy_id, self.run.idea_id, owner_id=test_owner_id())
        self.assertEqual(ctx.exception.status_code, 409)
        self.assertEqual(ctx.exception.detail["workflow_run_id"], str(first.id))
        after = self.db.query(ScheduledJob).filter(ScheduledJob.job_type == JobType.WORKFLOW_RUN).count()
        self.assertEqual(before, after)

    def test_enqueue_rejects_unknown_action(self):
        with self.assertRaises(ValueError):
            enqueue_workflow_job(self.db, "publish", uuid4())


class TestWorkerClaim(IsolatedDB):
    def test_claim_start_is_atomic_and_only_once(self):
        run = create_workflow_run(self.db, self.run.strategy_id, self.run.idea_id, owner_id=test_owner_id())
        self.assertTrue(claim_run_start(self.db, run.id))
        self.assertFalse(claim_run_start(self.db, run.id))
        self.db.refresh(run)
        self.assertEqual(run.status, WorkflowRunStatus.RUNNING)

    def test_duplicate_start_job_does_not_run_the_graph_twice(self):
        run = create_workflow_run(self.db, self.run.strategy_id, self.run.idea_id, owner_id=test_owner_id())
        scheduler = JobScheduler(worker_id="test-workflow")
        with patch("app.scheduler.service.SessionLocal", side_effect=self.session_factory), \
             patch("app.graph.content_graph.run_workflow_graph_background") as graph:
            first = scheduler._run_workflow_job({"action": "start", "workflow_run_id": str(run.id)})
            second = scheduler._run_workflow_job({"action": "start", "workflow_run_id": str(run.id)})
        self.assertEqual(first["status"], "started")
        self.assertEqual(second["status"], "skipped")
        graph.assert_called_once()

    def test_resume_job_calls_resume_with_the_decision(self):
        scheduler = JobScheduler(worker_id="test-workflow")
        decision = {"decision": "APPROVED", "feedback": None}
        with patch("app.graph.content_graph.resume_workflow_graph_background") as resume:
            result = scheduler._run_workflow_job(
                {"action": "resume", "workflow_run_id": str(self.run.id), "decision": decision}
            )
        self.assertEqual(result["status"], "resumed")
        resume.assert_called_once_with(str(self.run.id), decision)


class TestLeaseRenewal(IsolatedDB):
    def test_renewal_moves_claimed_at_forward_for_the_owning_worker_only(self):
        old = datetime.now(timezone.utc) - timedelta(minutes=10)
        job = ScheduledJob(
            owner_id=test_owner_id(),
            id=uuid4(), job_type=JobType.WORKFLOW_RUN, status=JobStatus.RUNNING,
            scheduled_at=old, claimed_at=old, claimed_by="owner-worker", payload={"action": "start"},
        )
        self.db.add(job)
        self.db.commit()

        LeaseKeeper(job.id, "owner-worker", session_factory=self.session_factory).renew_once()
        self.db.refresh(job)
        self.assertGreater(job.claimed_at.astimezone(timezone.utc), old + timedelta(minutes=5))

        job.claimed_at = old
        job.claimed_by = "someone-else"
        self.db.commit()
        LeaseKeeper(job.id, "owner-worker", session_factory=self.session_factory).renew_once()
        self.db.refresh(job)
        self.assertEqual(job.claimed_at.astimezone(timezone.utc), old)


if __name__ == "__main__":
    unittest.main()
