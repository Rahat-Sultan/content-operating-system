import os
import unittest
from unittest.mock import MagicMock, patch
from uuid import uuid4
from datetime import datetime, timezone
from fastapi import HTTPException
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
from app.analytics.service import sync_publication_metrics

from tests.test_publishing_concurrency import seed_test_workflow_tree

class TestAnalyticsSyncPaths(unittest.TestCase):
    def setUp(self):
        self.db = SessionLocal()
        # Create an isolated test tree
        run, content, v1 = seed_test_workflow_tree(self.db, run_status=WorkflowRunStatus.COMPLETED, approved=True)
        self.run = run
        self.content = content
        self.version = v1

        # Create a test publication
        self.pub = Publication(
            id=uuid4(),
            content_version_id=self.version.id,
            platform="linkedin",
            status=PublicationStatus.PUBLISHED,
            idempotency_key=f"test-sync-{uuid4()}",
            external_id=f"test-ext-{uuid4().hex[:10]}",
        )
        self.db.add(self.pub)
        self.db.commit()
        self.db.refresh(self.pub)

    def tearDown(self):
        # Clean up any created analytics snapshots, publication, and workflow tree
        self.db.query(Analytics).filter(Analytics.publication_id == self.pub.id).delete()
        self.db.delete(self.pub)
        self.db.commit()

        # Delete approval if exists
        self.db.execute(text("DELETE FROM approvals WHERE content_version_id = :vid"), {"vid": self.version.id})
        self.db.execute(text("DELETE FROM content_versions WHERE id = :vid"), {"vid": self.version.id})
        self.db.execute(text("DELETE FROM content WHERE id = :cid"), {"cid": self.content.id})
        self.db.execute(text("DELETE FROM workflow_runs WHERE id = :rid"), {"rid": self.run.id})
        self.db.commit()
        self.db.close()

    @patch("app.analytics.service.get_analytics_provider")
    def test_path1_success_writes_snapshot(self, mock_get_provider):
        mock_provider = MagicMock()
        mock_provider.fetch_metrics.return_value = AnalyticsResult(
            publication_id=self.pub.id,
            platform="linkedin",
            external_post_id=self.pub.external_id,
            metrics={"impressions": 1234, "likes": 56, "is_stub": False, "is_initial": False},
            collected_at=datetime.now(timezone.utc),
            provider="buffer",
        )
        mock_get_provider.return_value = mock_provider

        initial_count = self.db.query(Analytics).filter(Analytics.publication_id == self.pub.id).count()
        snapshot = sync_publication_metrics(self.db, self.pub.id)

        self.assertIsNotNone(snapshot.id)
        self.assertEqual(snapshot.metrics["impressions"], 1234)
        new_count = self.db.query(Analytics).filter(Analytics.publication_id == self.pub.id).count()
        self.assertEqual(new_count, initial_count + 1)

    @patch("app.analytics.service.get_analytics_provider")
    def test_path2_metrics_not_available_returns_409_no_snapshot(self, mock_get_provider):
        mock_provider = MagicMock()
        mock_provider.fetch_metrics.side_effect = MetricsNotAvailableError(
            "Metrics for post are not yet available from Buffer (propagation delay)."
        )
        mock_get_provider.return_value = mock_provider

        initial_count = self.db.query(Analytics).filter(Analytics.publication_id == self.pub.id).count()
        with self.assertRaises(HTTPException) as cm:
            sync_publication_metrics(self.db, self.pub.id)

        self.assertEqual(cm.exception.status_code, 409)
        self.assertIn("Metrics not yet available", cm.exception.detail)

        # Confirm NO snapshot row was written
        new_count = self.db.query(Analytics).filter(Analytics.publication_id == self.pub.id).count()
        self.assertEqual(new_count, initial_count)

    @patch("app.analytics.service.get_analytics_provider")
    def test_path3_post_not_found_returns_404_no_snapshot(self, mock_get_provider):
        mock_provider = MagicMock()
        mock_provider.fetch_metrics.side_effect = PostNotFoundError(
            "Post not found on Buffer (permanent 404)."
        )
        mock_get_provider.return_value = mock_provider

        initial_count = self.db.query(Analytics).filter(Analytics.publication_id == self.pub.id).count()
        with self.assertRaises(HTTPException) as cm:
            sync_publication_metrics(self.db, self.pub.id)

        self.assertEqual(cm.exception.status_code, 404)
        self.assertIn("Post not found on analytics provider", cm.exception.detail)

        # Confirm NO snapshot row was written
        new_count = self.db.query(Analytics).filter(Analytics.publication_id == self.pub.id).count()
        self.assertEqual(new_count, initial_count)

    @patch("app.analytics.service.get_analytics_provider")
    def test_path4_metrics_unsupported_returns_422_no_snapshot(self, mock_get_provider):
        from app.analytics.interface import MetricsUnsupportedError
        mock_provider = MagicMock()
        mock_provider.fetch_metrics.side_effect = MetricsUnsupportedError(
            "Analytics are not supported for this channel type."
        )
        mock_get_provider.return_value = mock_provider

        initial_count = self.db.query(Analytics).filter(Analytics.publication_id == self.pub.id).count()
        with self.assertRaises(HTTPException) as cm:
            sync_publication_metrics(self.db, self.pub.id)

        self.assertEqual(cm.exception.status_code, 422)
        self.assertIn("Metrics unsupported", cm.exception.detail)

        # Confirm NO snapshot row was written
        new_count = self.db.query(Analytics).filter(Analytics.publication_id == self.pub.id).count()
        self.assertEqual(new_count, initial_count)


class TestBufferProviderGating(unittest.TestCase):
    """
    CP-1.2: Tests using fixtures covering:
    1. Real metrics with metricsUpdatedAt > sentAt -> snapshot returned
    2. Null or uncollected metricsUpdatedAt (metricsUpdatedAt <= sentAt) -> MetricsNotAvailableError
    3. Populated metricsUpdatedAt > sentAt with genuine zeros -> snapshot returned
    4. Unsupported channel error -> MetricsUnsupportedError
    """

    @patch("app.analytics.buffer_provider.BufferAnalyticsProvider._execute_graphql")
    def test_provider_real_metrics_returns_result(self, mock_gql):
        from app.analytics.buffer_provider import BufferAnalyticsProvider
        from app.analytics.interface import AnalyticsRequest
        mock_gql.return_value = {
            "data": {
                "post": {
                    "id": "ext-123",
                    "status": "sent",
                    "sentAt": "2026-10-05T07:00:00.000Z",
                    "metricsUpdatedAt": "2026-10-05T08:00:00.000Z",
                    "metrics": [
                        {"name": "Reactions", "type": "reactions", "value": 5},
                        {"name": "Comments", "type": "comments", "value": 2},
                        {"name": "Impressions", "type": "impressions", "value": 150},
                    ]
                }
            }
        }
        provider = BufferAnalyticsProvider(access_token="test-token")
        req = AnalyticsRequest(publication_id=uuid4(), platform="linkedin", external_post_id="ext-123")
        res = provider.fetch_metrics(req)
        self.assertEqual(res.metrics["impressions"], 150)
        self.assertEqual(res.metrics["reactions"], 5)
        self.assertEqual(res.metrics["comments"], 2)

    @patch("app.analytics.buffer_provider.BufferAnalyticsProvider._execute_graphql")
    def test_provider_uncollected_placeholder_raises_not_available(self, mock_gql):
        from app.analytics.buffer_provider import BufferAnalyticsProvider
        from app.analytics.interface import AnalyticsRequest, MetricsNotAvailableError
        # metricsUpdatedAt is before sentAt (the real Buffer placeholder pattern)
        mock_gql.return_value = {
            "data": {
                "post": {
                    "id": "ext-123",
                    "status": "sent",
                    "sentAt": "2026-10-05T07:39:00.550Z",
                    "metricsUpdatedAt": "2026-10-05T07:38:59.501Z",
                    "metrics": [
                        {"name": "Reactions", "type": "reactions", "value": 0},
                        {"name": "Comments", "type": "comments", "value": 0},
                    ]
                }
            }
        }
        provider = BufferAnalyticsProvider(access_token="test-token")
        req = AnalyticsRequest(publication_id=uuid4(), platform="linkedin", external_post_id="ext-123")
        with self.assertRaises(MetricsNotAvailableError):
            provider.fetch_metrics(req)

    @patch("app.analytics.buffer_provider.BufferAnalyticsProvider._execute_graphql")
    def test_provider_null_metrics_updated_at_raises_not_available(self, mock_gql):
        from app.analytics.buffer_provider import BufferAnalyticsProvider
        from app.analytics.interface import AnalyticsRequest, MetricsNotAvailableError
        mock_gql.return_value = {
            "data": {
                "post": {
                    "id": "ext-123",
                    "status": "sent",
                    "sentAt": "2026-10-05T07:39:00.550Z",
                    "metricsUpdatedAt": None,
                    "metrics": []
                }
            }
        }
        provider = BufferAnalyticsProvider(access_token="test-token")
        req = AnalyticsRequest(publication_id=uuid4(), platform="linkedin", external_post_id="ext-123")
        with self.assertRaises(MetricsNotAvailableError):
            provider.fetch_metrics(req)

    @patch("app.analytics.buffer_provider.BufferAnalyticsProvider._execute_graphql")
    def test_provider_genuine_zeros_with_fresh_updated_at_returns_result(self, mock_gql):
        from app.analytics.buffer_provider import BufferAnalyticsProvider
        from app.analytics.interface import AnalyticsRequest
        # Genuine collection ran subsequent day, truly 0 engagement
        mock_gql.return_value = {
            "data": {
                "post": {
                    "id": "ext-123",
                    "status": "sent",
                    "sentAt": "2026-10-02T06:59:31.615Z",
                    "metricsUpdatedAt": "2026-10-05T02:31:54.002Z",
                    "metrics": [
                        {"name": "Reactions", "type": "reactions", "value": 0},
                        {"name": "Comments", "type": "comments", "value": 0},
                    ]
                }
            }
        }
        provider = BufferAnalyticsProvider(access_token="test-token")
        req = AnalyticsRequest(publication_id=uuid4(), platform="linkedin", external_post_id="ext-123")
        res = provider.fetch_metrics(req)
        self.assertEqual(res.metrics["reactions"], 0)
        self.assertEqual(res.metrics["comments"], 0)
        self.assertEqual(res.metrics["metrics_updated_at"], "2026-10-05T02:31:54.002Z")


if __name__ == "__main__":
    unittest.main()

