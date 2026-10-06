"""
Stop-and-delete for an idea: queued work is removed, a running step is waited for,
a publishing run blocks the delete, and another account's idea is never touched.
Runs in one rolled-back transaction on the real database.
"""
import os
import unittest
from datetime import datetime, timezone
from uuid import uuid4

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "../backend/.env"))

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.accounts.models import User
from app.db import engine
from app.ideas.lifecycle import stop_and_delete_idea
from app.ideas.models import Idea
from app.scheduler.models import JobStatus, JobType, ScheduledJob
from app.workflows.models import WorkflowRun, WorkflowRunStatus
from tests.test_publishing_concurrency import seed_test_workflow_tree, test_owner_id


class Isolated(unittest.TestCase):
    def setUp(self):
        self.connection = engine.connect()
        self.outer = self.connection.begin()
        self.db = Session(bind=self.connection, join_transaction_mode="create_savepoint")
        self.owner = test_owner_id()
        self.run, _, _ = seed_test_workflow_tree(self.db, run_status=WorkflowRunStatus.PENDING, approved=False)
        self.idea_id = self.run.idea_id
        self.run_id = self.run.id

    def tearDown(self):
        self.db.close()
        self.outer.rollback()
        self.connection.close()

    def queue_job(self, status):
        job = ScheduledJob(id=uuid4(), owner_id=self.owner, job_type=JobType.WORKFLOW_RUN, status=status,
                           scheduled_at=datetime.now(timezone.utc),
                           payload={"action": "start", "workflow_run_id": str(self.run_id)})
        self.db.add(job)
        self.db.commit()
        return job


class TestStopAndDelete(Isolated):
    def test_queued_work_is_removed_and_the_idea_deleted(self):
        pending = self.queue_job(JobStatus.PENDING)
        result = stop_and_delete_idea(self.db, self.idea_id, self.owner)
        self.assertEqual(result["status"], "deleted")
        self.assertIsNone(self.db.query(Idea).filter(Idea.id == self.idea_id).first())
        self.assertIsNone(self.db.query(WorkflowRun).filter(WorkflowRun.id == self.run_id).first())
        job = self.db.query(ScheduledJob).filter(ScheduledJob.id == pending.id).one()
        self.assertEqual(job.status, JobStatus.FAILED)
        self.assertIn("stopped", job.error)  # kept as a record, never run

    def test_running_step_is_waited_for_and_not_deleted_yet(self):
        self.queue_job(JobStatus.RUNNING)
        result = stop_and_delete_idea(self.db, self.idea_id, self.owner)
        self.assertEqual(result["status"], "stopping")
        self.assertIsNotNone(self.db.query(Idea).filter(Idea.id == self.idea_id).first())
        run = self.db.query(WorkflowRun).filter(WorkflowRun.id == self.run_id).one()
        self.assertEqual(run.status, WorkflowRunStatus.CANCELLED)

    def test_publishing_run_blocks_the_delete(self):
        self.run.status = WorkflowRunStatus.PUBLISHING
        self.db.commit()
        with self.assertRaises(HTTPException) as ctx:
            stop_and_delete_idea(self.db, self.idea_id, self.owner)
        self.assertEqual(ctx.exception.status_code, 409)
        run = self.db.query(WorkflowRun).filter(WorkflowRun.id == self.run_id).one()
        self.assertEqual(run.status, WorkflowRunStatus.PUBLISHING)

    def test_another_accounts_idea_is_not_touched(self):
        stranger = User(id=uuid4(), email=f"stranger-{uuid4().hex[:8]}@example.test", display_name="x",
                        password_hash=None, auth_provider="local")
        self.db.add(stranger)
        self.db.commit()
        with self.assertRaises(HTTPException) as ctx:
            stop_and_delete_idea(self.db, self.idea_id, stranger.id)
        self.assertEqual(ctx.exception.status_code, 404)
        self.assertIsNotNone(self.db.query(Idea).filter(Idea.id == self.idea_id).first())


if __name__ == "__main__":
    unittest.main()
