"""
Sources get a short default name from their link, and that name is always editable
afterward. Runs inside one transaction on a single connection, rolled back in tearDown,
so the real contentos_dev data is untouched.
"""
import os
import unittest
from uuid import uuid4

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "../backend/.env"))

from sqlalchemy.orm import Session

from app.db import engine
from app.accounts.models import User
from app.sources.service import create_source, update_source


class SourceRenameTest(unittest.TestCase):
    def setUp(self):
        self.connection = engine.connect()
        self.outer = self.connection.begin()
        self.db = Session(bind=self.connection, join_transaction_mode="create_savepoint")
        self.owner = User(id=uuid4(), email=f"rename-{uuid4()}@example.test", display_name="Rename", auth_provider="local")
        self.db.add(self.owner)
        self.db.flush()

    def tearDown(self):
        self.db.close()
        self.outer.rollback()
        self.connection.close()

    def test_new_source_gets_a_short_domain_name_by_default(self):
        source = create_source(self.db, name=None, url="https://krebsonsecurity.com/feed/", owner_id=self.owner.id)
        self.assertEqual(source.name, "krebsonsecurity")

    def test_a_typed_name_is_kept_as_given(self):
        source = create_source(self.db, name="Krebs on Security", url="https://krebsonsecurity.com/feed/", owner_id=self.owner.id)
        self.assertEqual(source.name, "Krebs on Security")

    def test_rename_an_existing_source(self):
        source = create_source(self.db, name=None, url="https://krebsonsecurity.com/feed/", owner_id=self.owner.id)
        updated = update_source(self.db, source.id, owner_id=self.owner.id, name="Krebs")
        self.assertEqual(updated.name, "Krebs")

    def test_changing_the_link_relabels_an_auto_named_source(self):
        source = create_source(self.db, name=None, url="https://krebsonsecurity.com/feed/", owner_id=self.owner.id)
        updated = update_source(self.db, source.id, owner_id=self.owner.id, url="https://theregister.com/security/headlines.atom")
        self.assertEqual(updated.name, "theregister")

    def test_changing_the_link_does_not_overwrite_a_hand_picked_name(self):
        source = create_source(self.db, name="Krebs", url="https://krebsonsecurity.com/feed/", owner_id=self.owner.id)
        updated = update_source(self.db, source.id, owner_id=self.owner.id, url="https://theregister.com/security/headlines.atom")
        self.assertEqual(updated.name, "Krebs")


if __name__ == "__main__":
    unittest.main()
