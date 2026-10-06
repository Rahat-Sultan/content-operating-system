import os
import unittest
from tests.test_publishing_concurrency import test_owner_id
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from app.strategies.models import ContentStrategy
from app.publishing.models import Publication, PublicationStatus
from app.scheduler.schedule_calculator import (
    is_strategy_discovery_due,
    get_next_analytics_sync_time,
    ANALYTICS_BACKOFF_MINUTES,
)


class TestScheduleCalculations(unittest.TestCase):
    def test_discovery_due_never_run(self):
        strat = ContentStrategy(
            owner_id=test_owner_id(),
            id=uuid4(),
            name="Test Strat",
            config={"discovery_interval_hours": 4},
            enabled=True,
        )
        self.assertTrue(is_strategy_discovery_due(strat, last_run_time=None))

    def test_discovery_due_disabled_strategy(self):
        strat = ContentStrategy(
            owner_id=test_owner_id(),
            id=uuid4(),
            name="Test Strat",
            config={"discovery_interval_hours": 4},
            enabled=False,
        )
        self.assertFalse(is_strategy_discovery_due(strat, last_run_time=None))

    def test_discovery_due_no_interval_configured(self):
        strat = ContentStrategy(
            owner_id=test_owner_id(),
            id=uuid4(),
            name="Test Strat",
            config={},
            enabled=True,
        )
        self.assertFalse(is_strategy_discovery_due(strat, last_run_time=None))

    def test_discovery_due_ran_recently(self):
        now = datetime.now(timezone.utc)
        strat = ContentStrategy(
            owner_id=test_owner_id(),
            id=uuid4(),
            name="Test Strat",
            config={"discovery_interval_hours": 4},
            enabled=True,
        )
        last_run = now - timedelta(hours=2)
        self.assertFalse(is_strategy_discovery_due(strat, last_run_time=last_run, now=now))

    def test_discovery_due_overdue(self):
        now = datetime.now(timezone.utc)
        strat = ContentStrategy(
            owner_id=test_owner_id(),
            id=uuid4(),
            name="Test Strat",
            config={"discovery_interval_hours": 4},
            enabled=True,
        )
        last_run = now - timedelta(hours=5)
        self.assertTrue(is_strategy_discovery_due(strat, last_run_time=last_run, now=now))

    def test_discovery_due_enforces_minimum_interval(self):
        # Even if config specifies 0.1 hours, default min interval is 1.0 hour
        now = datetime.now(timezone.utc)
        strat = ContentStrategy(
            owner_id=test_owner_id(),
            id=uuid4(),
            name="Test Strat",
            config={"discovery_interval_hours": 0.1},
            enabled=True,
        )
        last_run = now - timedelta(minutes=30)  # 0.5 hours ago
        self.assertFalse(is_strategy_discovery_due(strat, last_run_time=last_run, now=now))

    def test_analytics_sync_backoff_schedule(self):
        base_time = datetime(2026, 10, 5, 12, 0, 0, tzinfo=timezone.utc)
        pub = Publication(
            owner_id=test_owner_id(),
            id=uuid4(),
            status=PublicationStatus.PUBLISHED,
            external_id="ext-12345",
            published_at=base_time,
        )

        # Attempt 0: 15 min
        next_t0 = get_next_analytics_sync_time(pub, 0)
        self.assertEqual(next_t0, base_time + timedelta(minutes=15))

        # Attempt 1: 60 min (1 h)
        next_t1 = get_next_analytics_sync_time(pub, 1)
        self.assertEqual(next_t1, base_time + timedelta(minutes=60))

        # Attempt 5: 10080 min (7 d)
        next_t5 = get_next_analytics_sync_time(pub, 5)
        self.assertEqual(next_t5, base_time + timedelta(minutes=10080))

        # Attempt 6 (past the ladder): daily check, 24 h after the last attempt
        last = base_time + timedelta(days=7)
        next_t6 = get_next_analytics_sync_time(pub, 6, last_attempt_time=last)
        self.assertEqual(next_t6, last + timedelta(hours=24))

    def test_daily_polling_stops_after_the_window(self):
        published = datetime.now(timezone.utc) - timedelta(days=31)
        pub = Publication(owner_id=test_owner_id(), id=uuid4(), status=PublicationStatus.PUBLISHED,
                          external_id="6ac3541363761da98b71e85b", published_at=published)
        last = published + timedelta(days=29, hours=20)
        self.assertIsNone(get_next_analytics_sync_time(pub, 9, last_attempt_time=last))

        # Same publication, last attempt 5 days in: still inside the window.
        inside = published + timedelta(days=5)
        pub.published_at = published
        self.assertIsNotNone(get_next_analytics_sync_time(pub, 9, last_attempt_time=inside))

    def test_analytics_sync_skips_non_published_or_missing_id(self):
        pub_pending = Publication(
            owner_id=test_owner_id(),
            id=uuid4(),
            status=PublicationStatus.PENDING,
            external_id="ext-123",
        )
        self.assertIsNone(get_next_analytics_sync_time(pub_pending, 0))

        pub_no_ext = Publication(
            owner_id=test_owner_id(),
            id=uuid4(),
            status=PublicationStatus.PUBLISHED,
            external_id=None,
        )
        self.assertIsNone(get_next_analytics_sync_time(pub_no_ext, 0))

    def test_analytics_sync_skips_non_buffer_ids(self):
        # Local-test and invalid ids are never sent to Buffer.
        for ext in ("linkedin_abc123", "test-ext-1", "stub_9", "buffer_idea_6abf35338a74c61099923dab"):
            pub = Publication(
                owner_id=test_owner_id(),
                id=uuid4(),
                status=PublicationStatus.PUBLISHED,
                external_id=ext,
                published_at=datetime.now(timezone.utc) - timedelta(days=1),
            )
            with self.subTest(ext=ext):
                self.assertIsNone(get_next_analytics_sync_time(pub, 0))


if __name__ == "__main__":
    unittest.main()
