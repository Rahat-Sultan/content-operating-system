"""
Default sources for new accounts and the suggestion list. Runs inside one transaction
on a single connection, rolled back in tearDown, so the real contentos_dev data is untouched.
"""
import os
import unittest
from uuid import uuid4

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "../backend/.env"))

from sqlalchemy.orm import Session

from app.db import engine
from app.accounts.models import User
from app.sources.catalog import SUGGESTED_SOURCES, seed_default_sources, suggestions_for
from app.sources.models import Source


class SourceDefaultsTest(unittest.TestCase):
    def setUp(self):
        self.connection = engine.connect()
        self.outer = self.connection.begin()
        self.db = Session(bind=self.connection, join_transaction_mode="create_savepoint")
        self.user = User(id=uuid4(), email=f"defaults-{uuid4()}@example.test",
                         display_name="Defaults", auth_provider="local")
        self.db.add(self.user)
        self.db.flush()

    def tearDown(self):
        self.db.close()
        self.outer.rollback()
        self.connection.close()

    def test_new_account_gets_exactly_the_default_sources(self):
        added = seed_default_sources(self.db, self.user.id)
        expected = [e for e in SUGGESTED_SOURCES if e["default"]]
        self.assertEqual(added, len(expected))
        rows = self.db.query(Source).filter(Source.owner_id == self.user.id).all()
        self.assertEqual(sorted(r.url for r in rows), sorted(e["url"] for e in expected))
        self.assertTrue(all(r.source_type == "rss" and r.enabled for r in rows))

    def test_suggestions_hide_what_the_account_already_has(self):
        seed_default_sources(self.db, self.user.id)
        remaining = {s["url"] for s in suggestions_for(self.db, self.user.id)}
        defaults = {e["url"] for e in SUGGESTED_SOURCES if e["default"]}
        self.assertFalse(remaining & defaults)
        self.assertEqual(
            remaining, {e["url"] for e in SUGGESTED_SOURCES} - defaults
        )

    def test_every_suggestion_is_an_http_feed_url(self):
        for e in SUGGESTED_SOURCES:
            with self.subTest(name=e["name"]):
                self.assertTrue(e["url"].startswith(("https://", "http://")))


if __name__ == "__main__":
    unittest.main()
