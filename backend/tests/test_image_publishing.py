"""
Image attachment for Buffer posts. Buffer fetches the image from a public HTTPS URL.

Isolated: every DB test runs in one rolled-back transaction on the real database.
Buffer HTTP is mocked, so nothing is sent to Buffer.
"""
import os
import unittest
from unittest.mock import patch
from uuid import uuid4

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "../backend/.env"))

from sqlalchemy.orm import Session

from app.config import settings
from app.db import engine
from app.media.models import MediaAsset, MediaAssetStatus, MediaAssetType
from app.media.public_url import buffer_assets_for, public_image_url_for_version
from app.publishing.buffer_provider import BufferPublisher
from app.publishing.interface import PermanentPublishingError, PublishRequest
from app.workflows.models import WorkflowRunStatus
from tests.test_publishing_concurrency import seed_test_workflow_tree


class TestAssetShape(unittest.TestCase):
    def test_no_image_means_no_assets(self):
        self.assertEqual(buffer_assets_for(None), [])

    def test_image_is_sent_as_buffer_image_asset(self):
        self.assertEqual(
            buffer_assets_for("https://media.example.com/api/media/files/a.png"),
            [{"image": {"url": "https://media.example.com/api/media/files/a.png"}}],
        )


class TestPublicUrl(unittest.TestCase):
    def setUp(self):
        self.connection = engine.connect()
        self.outer = self.connection.begin()
        self.db = Session(bind=self.connection, join_transaction_mode="create_savepoint")
        self.run, self.content, self.version = seed_test_workflow_tree(
            self.db, run_status=WorkflowRunStatus.COMPLETED, approved=True
        )
        self._base = settings.media_public_base_url

    def tearDown(self):
        settings.media_public_base_url = self._base
        self.db.close()
        self.outer.rollback()
        self.connection.close()

    def _add_image(self, status=MediaAssetStatus.READY):
        self.db.add(MediaAsset(
            id=uuid4(), content_version_id=self.version.id, type=MediaAssetType.IMAGE, status=status,
            storage_url="/api/media/files/dummy-test.png", mime_type="image/png",
            prompt="dummy test image", provider="local_test", asset_metadata={"is_stub": True},
        ))
        self.db.commit()

    def test_version_without_image_has_no_url(self):
        settings.media_public_base_url = "https://media.example.com"
        self.assertIsNone(public_image_url_for_version(self.db, self.version.id))

    def test_ready_image_gets_public_url(self):
        settings.media_public_base_url = "https://media.example.com/"
        self._add_image()
        self.assertEqual(
            public_image_url_for_version(self.db, self.version.id),
            "https://media.example.com/api/media/files/dummy-test.png",
        )

    def test_image_without_public_base_fails_loudly(self):
        settings.media_public_base_url = ""
        self._add_image()
        with self.assertRaises(PermanentPublishingError):
            public_image_url_for_version(self.db, self.version.id)

    def test_http_base_is_rejected(self):
        settings.media_public_base_url = "http://localhost:8000"
        self._add_image()
        with self.assertRaises(PermanentPublishingError):
            public_image_url_for_version(self.db, self.version.id)

    def test_pending_image_is_not_attached(self):
        settings.media_public_base_url = "https://media.example.com"
        self._add_image(status=MediaAssetStatus.PENDING)
        self.assertIsNone(public_image_url_for_version(self.db, self.version.id))


class TestBufferCreatePostInput(unittest.TestCase):
    """The createPost input carries the image asset when the request has one."""

    def _publish(self, metadata):
        publisher = BufferPublisher(access_token="test-token", channel_id="ch-1", organization_id="org-1")
        captured = {}

        def fake_graphql(client, query, variables=None):
            captured["variables"] = variables
            return {"data": {"createPost": {"__typename": "PostActionSuccess",
                                            "post": {"id": "post-1", "status": "sent", "externalLink": None}}}}

        request = PublishRequest(
            workflow_run_id=uuid4(), content_version_id=uuid4(), platform="linkedin",
            title="t", body="A short plain post.", idempotency_key="k", metadata=metadata,
        )
        with patch.object(BufferPublisher, "_resolve_organization", return_value=("org-1", 1)), \
             patch.object(BufferPublisher, "_resolve_channel_for_platform", return_value={"id": "ch-1", "name": "x"}), \
             patch.object(BufferPublisher, "_execute_graphql", side_effect=fake_graphql):
            publisher.publish(request)
        return captured["variables"]["input"]

    def test_text_only_post_has_empty_assets(self):
        self.assertEqual(self._publish({})["assets"], [])

    def test_image_post_carries_the_public_url(self):
        url = "https://media.example.com/api/media/files/dummy-test.png"
        self.assertEqual(self._publish({"image_url": url})["assets"], [{"image": {"url": url}}])


if __name__ == "__main__":
    unittest.main()
