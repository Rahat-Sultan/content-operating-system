import unittest
from tests.test_publishing_concurrency import test_owner_id
from uuid import uuid4
from datetime import datetime

from app.db import SessionLocal
from app.content.models import Content, ContentVersion, ContentVersionOrigin
from app.media.models import MediaAsset, MediaAssetType, MediaAssetStatus
from app.media.local_provider import LocalTestImageGenerationProvider
from app.media.interface import (
    ImageGenerationRequest,
    TransientImageGenerationError,
    PermanentImageGenerationError,
)
from app.media.local_storage import LocalFileMediaStorage
from app.media.service import generate_media_for_content_version, get_media_assets_for_content_version
from app.workflows.models import WorkflowRun, WorkflowRunStatus
from app.ideas.models import Idea, IdeaStatus
from app.strategies.models import ContentStrategy


class TestMediaAssetVersionSafety(unittest.TestCase):
    def setUp(self):
        self.db = SessionLocal()
        # Create test strategy, idea, workflow_run, and content
        self.strategy = ContentStrategy(
            owner_id=test_owner_id(),
            name="Media Test Strategy",
            config={"target_audience": "Engineers"},
            enabled=True,
        )
        self.db.add(self.strategy)
        self.db.flush()

        self.idea = Idea(
            owner_id=test_owner_id(),
            strategy_id=self.strategy.id,
            title="Media Test Idea",
            status=IdeaStatus.IN_PROGRESS,
            scoring_metadata={},
        )
        self.db.add(self.idea)
        self.db.flush()

        self.workflow_run = WorkflowRun(
            owner_id=test_owner_id(),
            idea_id=self.idea.id,
            strategy_id=self.strategy.id,
            status=WorkflowRunStatus.NEEDS_REVIEW,
            run_metadata={},
        )
        self.db.add(self.workflow_run)
        self.db.flush()

        self.content = Content(
            workflow_run_id=self.workflow_run.id,
        )
        self.db.add(self.content)
        self.db.flush()

    def tearDown(self):
        self.db.rollback()
        self.db.close()

    def test_version_isolation_and_immutability(self):
        """
        Verify that MediaAsset belongs strictly to an immutable ContentVersion.
        v1 has image A.
        v2 has image B.
        A belongs to v1; B belongs to v2. They never cross or overwrite each other.
        """
        # Create ContentVersion v1
        v1 = ContentVersion(
            content_id=self.content.id,
            version_number=1,
            origin=ContentVersionOrigin.WRITER_AGENT,
            title="Version 1 Title",
            body="Draft body v1",
        )
        self.db.add(v1)
        self.db.commit()

        # Generate Media for v1
        asset_v1 = generate_media_for_content_version(
            db=self.db,
            content_id=self.content.id,
            version_id=v1.id,
        )
        self.assertIsNotNone(asset_v1)
        self.assertEqual(asset_v1.content_version_id, v1.id)
        self.assertTrue(asset_v1.storage_url.startswith("/api/media/files/"))

        # Create ContentVersion v2 (revision)
        v2 = ContentVersion(
            content_id=self.content.id,
            version_number=2,
            origin=ContentVersionOrigin.HUMAN_EDIT,
            title="Version 2 Title (Revised)",
            body="Draft body v2 revised",
        )
        self.db.add(v2)
        self.db.commit()

        # Before generating for v2, verify v2 has NO assets
        assets_v2_before = get_media_assets_for_content_version(
            db=self.db,
            content_id=self.content.id,
            version_id=v2.id,
        )
        self.assertEqual(len(assets_v2_before), 0)

        # Generate Media for v2
        asset_v2 = generate_media_for_content_version(
            db=self.db,
            content_id=self.content.id,
            version_id=v2.id,
        )
        self.assertIsNotNone(asset_v2)
        self.assertEqual(asset_v2.content_version_id, v2.id)
        self.assertNotEqual(asset_v1.id, asset_v2.id)
        self.assertNotEqual(asset_v1.storage_url, asset_v2.storage_url)

        # Verify query for v1 still yields ONLY asset_v1
        assets_v1 = get_media_assets_for_content_version(
            db=self.db,
            content_id=self.content.id,
            version_id=v1.id,
        )
        self.assertEqual(len(assets_v1), 1)
        self.assertEqual(assets_v1[0].id, asset_v1.id)

        # Verify query for v2 yields ONLY asset_v2
        assets_v2 = get_media_assets_for_content_version(
            db=self.db,
            content_id=self.content.id,
            version_id=v2.id,
        )
        self.assertEqual(len(assets_v2), 1)
        self.assertEqual(assets_v2[0].id, asset_v2.id)

    def test_idempotent_generation_and_intentional_regeneration(self):
        """
        Verify repeat generation without regenerate flag returns existing asset.
        With regenerate=True, returns new distinct asset while keeping prior row intact.
        """
        v1 = ContentVersion(
            content_id=self.content.id,
            version_number=1,
            origin=ContentVersionOrigin.WRITER_AGENT,
            title="Idempotency Test",
            body="Draft body",
        )
        self.db.add(v1)
        self.db.commit()

        # First call
        asset1 = generate_media_for_content_version(
            db=self.db,
            content_id=self.content.id,
            version_id=v1.id,
        )

        # Second call (repeat/retry without flag)
        asset2 = generate_media_for_content_version(
            db=self.db,
            content_id=self.content.id,
            version_id=v1.id,
            regenerate=False,
        )
        self.assertEqual(asset1.id, asset2.id)

        # Third call (intentional regeneration)
        asset3 = generate_media_for_content_version(
            db=self.db,
            content_id=self.content.id,
            version_id=v1.id,
            regenerate=True,
        )
        self.assertNotEqual(asset1.id, asset3.id)

        # All assets are preserved
        all_assets = get_media_assets_for_content_version(
            db=self.db,
            content_id=self.content.id,
            version_id=v1.id,
        )
        self.assertEqual(len(all_assets), 2)

    def test_error_handling_classification(self):
        """Verify transient and permanent error classification."""
        transient_provider = LocalTestImageGenerationProvider(simulate_transient_failure=True)
        permanent_provider = LocalTestImageGenerationProvider(simulate_permanent_failure=True)

        req = ImageGenerationRequest(
            content_version_id=uuid4(),
            prompt="Test prompt",
        )

        with self.assertRaises(TransientImageGenerationError):
            transient_provider.generate_image(req)

        with self.assertRaises(PermanentImageGenerationError):
            permanent_provider.generate_image(req)


if __name__ == "__main__":
    unittest.main()
