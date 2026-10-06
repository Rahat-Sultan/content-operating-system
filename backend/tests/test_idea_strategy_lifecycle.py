"""
Archive, restore, delete, human edits and deleted-upstream marking.
Every test runs in one rolled-back transaction on the real database.
"""
import os
import unittest
from datetime import datetime, timezone
from uuid import uuid4

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "../backend/.env"))

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.db import engine
from app.ideas.lifecycle import (
    add_new_idea_if_unique, archive_idea, delete_idea, restore_idea,
    archive_strategy, restore_strategy, delete_strategy,
)
from app.ideas.models import Idea, IdeaStatus
from app.analytics.upstream import mark_deleted_upstream, deleted_upstream_at
from app.publishing.models import Publication, PublicationStatus
from app.scheduler.schedule_calculator import get_next_analytics_sync_time
from app.strategies.models import ContentStrategy
from app.workflows.models import WorkflowRunStatus
from app.workflows.service import create_human_edit_version
from app.content.models import ContentVersion
from tests.test_publishing_concurrency import test_owner_id, seed_test_workflow_tree


class Isolated(unittest.TestCase):
    def setUp(self):
        self.connection = engine.connect()
        self.outer = self.connection.begin()
        self.db = Session(bind=self.connection, join_transaction_mode="create_savepoint")

    def tearDown(self):
        self.db.close()
        self.outer.rollback()
        self.connection.close()

    def new_idea(self, strategy_id, title, status=IdeaStatus.NEW):
        idea = Idea(owner_id=test_owner_id(), id=uuid4(), strategy_id=strategy_id, title=title, status=status, scoring_metadata={})
        self.db.add(idea)
        self.db.commit()
        return idea


class TestArchiveRestoreDelete(Isolated):
    def setUp(self):
        super().setUp()
        self.run, self.content, self.version = seed_test_workflow_tree(
            self.db, run_status=WorkflowRunStatus.COMPLETED, approved=True
        )
        self.strategy_id = self.run.strategy_id

    def test_new_idea_archives_and_restores(self):
        idea = self.new_idea(self.strategy_id, f"TEST-{uuid4().hex[:6]}")
        self.assertEqual(archive_idea(self.db, idea.id, test_owner_id()).status, IdeaStatus.REJECTED)
        self.assertEqual(restore_idea(self.db, idea.id, test_owner_id()).status, IdeaStatus.NEW)

    def test_in_progress_idea_cannot_be_archived(self):
        idea = self.new_idea(self.strategy_id, f"TEST-{uuid4().hex[:6]}", status=IdeaStatus.IN_PROGRESS)
        with self.assertRaises(HTTPException) as ctx:
            archive_idea(self.db, idea.id, test_owner_id())
        self.assertEqual(ctx.exception.status_code, 409)

    def test_idea_with_a_run_cannot_be_deleted_but_an_unrun_one_can(self):
        with self.assertRaises(HTTPException) as ctx:
            delete_idea(self.db, self.run.idea_id, test_owner_id())
        self.assertEqual(ctx.exception.status_code, 409)
        unrun = self.new_idea(self.strategy_id, f"TEST-{uuid4().hex[:6]}")
        delete_idea(self.db, unrun.id, test_owner_id())
        self.assertIsNone(self.db.query(Idea).filter(Idea.id == unrun.id).first())

    def test_strategy_with_runs_cannot_be_deleted_but_archives(self):
        with self.assertRaises(HTTPException) as ctx:
            delete_strategy(self.db, self.strategy_id, test_owner_id())
        self.assertEqual(ctx.exception.status_code, 409)
        archive_strategy(self.db, self.strategy_id, test_owner_id())
        self.db.refresh(self.db.query(ContentStrategy).get(self.strategy_id))
        restore_strategy(self.db, self.strategy_id, test_owner_id())

    def test_duplicate_new_title_is_refused_by_the_index_and_skipped_by_discovery(self):
        title = f"TEST-{uuid4().hex[:6]}"
        self.new_idea(self.strategy_id, title)
        again = Idea(owner_id=test_owner_id(), id=uuid4(), strategy_id=self.strategy_id, title=title, status=IdeaStatus.NEW, scoring_metadata={})
        self.assertFalse(add_new_idea_if_unique(self.db, again))

    def test_discovery_skips_a_title_that_is_already_selected(self):
        title = f"TEST-{uuid4().hex[:6]}"
        self.new_idea(self.strategy_id, title, status=IdeaStatus.SELECTED)
        again = Idea(owner_id=test_owner_id(), id=uuid4(), strategy_id=self.strategy_id, title=title, status=IdeaStatus.NEW, scoring_metadata={})
        self.assertFalse(add_new_idea_if_unique(self.db, again))


class TestHumanEdit(Isolated):
    def setUp(self):
        super().setUp()
        self.run, self.content, self.version = seed_test_workflow_tree(
            self.db, run_status=WorkflowRunStatus.NEEDS_REVIEW, approved=False
        )

    def test_edit_creates_a_new_version_and_keeps_the_old_one(self):
        created = create_human_edit_version(self.db, self.run.id, "New title", "Edited body text.", owner_id=test_owner_id())
        self.assertEqual(created.version_number, self.version.version_number + 1)
        self.assertEqual(created.origin.value, "HUMAN_EDIT")
        self.db.refresh(self.version)
        self.assertNotEqual(self.version.body, "Edited body text.")

    def test_edit_refused_when_run_is_not_awaiting_review(self):
        self.run.status = WorkflowRunStatus.COMPLETED
        self.db.commit()
        with self.assertRaises(HTTPException) as ctx:
            create_human_edit_version(self.db, self.run.id, None, "x", owner_id=test_owner_id())
        self.assertEqual(ctx.exception.status_code, 409)


class TestDeletedUpstream(Isolated):
    def setUp(self):
        super().setUp()
        self.run, self.content, self.version = seed_test_workflow_tree(
            self.db, run_status=WorkflowRunStatus.COMPLETED, approved=True
        )
        self.pub = Publication(
            owner_id=test_owner_id(),
            id=uuid4(), content_version_id=self.version.id, platform="linkedin",
            status=PublicationStatus.PUBLISHED, idempotency_key=f"test-del-{uuid4()}",
            external_id="6ac3541363761da98b71e85b", published_at=datetime.now(timezone.utc),
        )
        self.db.add(self.pub)
        self.db.commit()

    def test_marked_post_stops_being_scheduled(self):
        self.assertIsNotNone(get_next_analytics_sync_time(self.pub, 0))
        mark_deleted_upstream(self.db, self.pub.id, "Post not found for id")
        self.db.refresh(self.pub)
        self.assertIsNotNone(deleted_upstream_at(self.pub))
        self.assertIsNone(get_next_analytics_sync_time(self.pub, 0))


if __name__ == "__main__":
    unittest.main()
