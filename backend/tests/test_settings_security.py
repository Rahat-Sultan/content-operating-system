"""
API keys per account: encrypted storage, owner scoping, and fallback to the installation default.
Database tests run in one rolled-back transaction.
"""
import os
import unittest
from unittest.mock import patch
from uuid import uuid4

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "../backend/.env"))

from cryptography.fernet import Fernet
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.accounts.models import User
from app.config import settings
from app.db import engine
from app.settings_security import crypto, service
from app.settings_security.models import SecretValue
from tests.test_publishing_concurrency import test_owner_id


class TestCrypto(unittest.TestCase):
    def test_api_key_round_trips_and_is_not_plain(self):
        with patch.object(settings, "settings_encryption_key", Fernet.generate_key().decode()):
            token = crypto.encrypt("test-key-value-0001")
            self.assertNotIn("key-value", token)
            self.assertEqual(crypto.decrypt(token), "test-key-value-0001")

    def test_missing_key_is_refused_not_silently_stored(self):
        with patch.object(settings, "settings_encryption_key", ""):
            with self.assertRaises(crypto.EncryptionKeyMissing):
                crypto.encrypt("anything-long-enough")


class Isolated(unittest.TestCase):
    def setUp(self):
        self.connection = engine.connect()
        self.outer = self.connection.begin()
        self.db = Session(bind=self.connection, join_transaction_mode="create_savepoint")
        self.owner = test_owner_id()
        self.other = self._other_account()

    def _other_account(self):
        user = User(id=uuid4(), email=f"other-{uuid4().hex[:8]}@example.test", display_name="Other",
                    password_hash=None, auth_provider="local")
        self.db.add(user)
        self.db.commit()
        return user.id

    def tearDown(self):
        self.db.close()
        self.outer.rollback()
        self.connection.close()


class TestKeysPerAccount(Isolated):
    def test_key_is_saved_encrypted_with_only_last4_in_clear(self):
        with patch.object(settings, "settings_encryption_key", Fernet.generate_key().decode()):
            service.set_key(self.db, self.owner, "OPENROUTER_API_KEY", "test-key-value-0002")
            row = self.db.query(SecretValue).filter(SecretValue.owner_id == self.owner,
                                                    SecretValue.name == "OPENROUTER_API_KEY").one()
            self.assertEqual(row.last4, "0002")
            self.assertNotIn("key-value", row.ciphertext)
            listed = {k["name"]: k for k in service.list_keys(self.db, self.owner)}
            self.assertTrue(listed["OPENROUTER_API_KEY"]["saved_in_app"])
            self.assertNotIn("test-key-value-0002", str(listed))

    def test_one_accounts_key_is_invisible_to_another(self):
        with patch.object(settings, "settings_encryption_key", Fernet.generate_key().decode()):
            service.set_key(self.db, self.owner, "BUFFER_ACCESS_TOKEN", "test-key-value-0003")
            mine = {k["name"]: k for k in service.list_keys(self.db, self.owner)}
            theirs = {k["name"]: k for k in service.list_keys(self.db, self.other)}
            self.assertTrue(mine["BUFFER_ACCESS_TOKEN"]["saved_in_app"])
            self.assertFalse(theirs["BUFFER_ACCESS_TOKEN"]["saved_in_app"])

    def test_key_for_prefers_the_accounts_own_key(self):
        with patch.object(settings, "settings_encryption_key", Fernet.generate_key().decode()):
            service.set_key(self.db, self.owner, "OPENROUTER_API_KEY", "test-key-value-0004")
            self.assertEqual(service.key_for(self.db, self.owner, "OPENROUTER_API_KEY"), "test-key-value-0004")
            # the other account has no key of its own, so it gets the installation default (or None)
            other = service.key_for(self.db, self.other, "OPENROUTER_API_KEY")
            self.assertNotEqual(other, "test-key-value-0004")

    def test_unknown_key_name_is_refused(self):
        with self.assertRaises(HTTPException) as ctx:
            service.set_key(self.db, self.owner, "AWS_SECRET", "something-long-enough")
        self.assertEqual(ctx.exception.status_code, 404)

    def test_key_with_spaces_is_refused(self):
        with self.assertRaises(HTTPException) as ctx:
            service.set_key(self.db, self.owner, "BUFFER_ACCESS_TOKEN", "has a space in it")
        self.assertEqual(ctx.exception.status_code, 422)


if __name__ == "__main__":
    unittest.main()
