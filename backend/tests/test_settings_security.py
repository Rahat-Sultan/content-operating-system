"""
Settings access: password, lockout, sessions, encrypted keys.
Database tests run in one rolled-back transaction; the real settings password is never changed.
"""
import os
import unittest
from unittest.mock import MagicMock, patch
from uuid import uuid4

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "../backend/.env"))

from cryptography.fernet import Fernet
from fastapi import HTTPException, Response
from sqlalchemy.orm import Session

from app.config import settings
from app.db import engine
from app.settings_security import crypto, service
from app.settings_security.models import SecretValue, SettingsAuth


class TestCrypto(unittest.TestCase):
    def test_password_hash_verifies_only_the_right_password(self):
        stored = crypto.hash_password("correct horse battery")
        self.assertTrue(crypto.verify_password("correct horse battery", stored))
        self.assertFalse(crypto.verify_password("wrong horse battery", stored))
        self.assertFalse(crypto.verify_password("x", "not-a-hash"))

    def test_hash_is_salted(self):
        self.assertNotEqual(crypto.hash_password("same-password-1"), crypto.hash_password("same-password-1"))

    def test_api_key_round_trips_and_is_not_plain(self):
        with patch.object(settings, "settings_encryption_key", Fernet.generate_key().decode()):
            token = crypto.encrypt("test-key-value-0001")
            self.assertNotIn("testvalue", token)
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
        self.db.query(SettingsAuth).delete()  # rolled back in tearDown
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.outer.rollback()
        self.connection.close()


class TestPasswordAndSessions(Isolated):
    def test_password_must_be_long_enough(self):
        with self.assertRaises(HTTPException) as ctx:
            service.setup_password(self.db, "short")
        self.assertEqual(ctx.exception.status_code, 422)

    def test_setup_then_login_creates_a_session_cookie_without_expiry(self):
        service.setup_password(self.db, "a-long-enough-password")
        response = Response()
        service.login(self.db, "a-long-enough-password", response)
        cookie = response.headers["set-cookie"]
        self.assertIn("HttpOnly", cookie)
        self.assertIn("samesite=strict", cookie.lower())
        self.assertNotIn("max-age", cookie.lower())   # ends with the browser session
        self.assertNotIn("expires=", cookie.lower())

    def test_wrong_password_is_refused(self):
        service.setup_password(self.db, "a-long-enough-password")
        with self.assertRaises(HTTPException) as ctx:
            service.login(self.db, "not-the-password", Response())
        self.assertEqual(ctx.exception.status_code, 401)

    def test_five_wrong_attempts_lock_the_page(self):
        service.setup_password(self.db, "a-long-enough-password")
        for _ in range(service.MAX_FAILED_ATTEMPTS):
            with self.assertRaises(HTTPException):
                service.login(self.db, "wrong-password-here", Response())
        with self.assertRaises(HTTPException) as ctx:
            service.login(self.db, "a-long-enough-password", Response())
        self.assertEqual(ctx.exception.status_code, 423)

    def test_no_session_means_locked(self):
        with self.assertRaises(HTTPException) as ctx:
            service.require_session(self.db, None)
        self.assertEqual(ctx.exception.status_code, 401)

    def test_logout_ends_the_session(self):
        service.setup_password(self.db, "a-long-enough-password")
        response = Response()
        service.login(self.db, "a-long-enough-password", response)
        token = response.headers["set-cookie"].split(";")[0].split("=", 1)[1]
        service.require_session(self.db, token)  # passes
        service.logout(self.db, token, Response())
        with self.assertRaises(HTTPException):
            service.require_session(self.db, token)


class TestKeys(Isolated):
    def test_key_is_saved_encrypted_and_only_last4_is_kept_in_clear(self):
        with patch.object(settings, "settings_encryption_key", Fernet.generate_key().decode()), \
             patch("app.settings_security.service.apply_saved_keys"):
            service.set_key(self.db, "OPENROUTER_API_KEY", "test-key-value-0002")
            row = self.db.query(SecretValue).filter(SecretValue.name == "OPENROUTER_API_KEY").one()
            self.assertEqual(row.last4, "0002")
            self.assertNotIn("key-value-0002", row.ciphertext)
            listed = {k["name"]: k for k in service.list_keys(self.db)}
            self.assertTrue(listed["OPENROUTER_API_KEY"]["saved_in_app"])
            self.assertNotIn("key-value-0002", str(listed))

    def test_unknown_key_name_is_refused(self):
        with self.assertRaises(HTTPException) as ctx:
            service.set_key(self.db, "AWS_SECRET", "something-long-enough")
        self.assertEqual(ctx.exception.status_code, 404)

    def test_key_with_spaces_is_refused(self):
        with self.assertRaises(HTTPException) as ctx:
            service.set_key(self.db, "BUFFER_ACCESS_TOKEN", "has a space in it")
        self.assertEqual(ctx.exception.status_code, 422)


if __name__ == "__main__":
    unittest.main()
