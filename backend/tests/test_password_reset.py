"""
Password change and the forgot-password code flow. Runs inside one transaction on a
single connection, rolled back in tearDown, so the real contentos_dev data is untouched.
"""
import os
import unittest
from datetime import timedelta
from unittest.mock import patch
from uuid import uuid4

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "../backend/.env"))

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.db import engine
from app.accounts.models import PasswordResetCode, User
from app.accounts.service import (
    RESET_CODE_MAX_ATTEMPTS,
    _now,
    change_password,
    confirm_password_reset,
    request_password_reset,
)
from app.settings_security.crypto import hash_password, verify_password


class PasswordResetTest(unittest.TestCase):
    def setUp(self):
        self.connection = engine.connect()
        self.outer = self.connection.begin()
        self.db = Session(bind=self.connection, join_transaction_mode="create_savepoint")
        self.local_user = User(
            id=uuid4(), email=f"reset-{uuid4()}@example.test", display_name="Local",
            password_hash=hash_password("original-password"), auth_provider="local",
        )
        self.google_user = User(
            id=uuid4(), email=f"google-{uuid4()}@example.test", display_name="Google",
            password_hash=None, auth_provider="google",
        )
        self.db.add_all([self.local_user, self.google_user])
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.outer.rollback()
        self.connection.close()

    def _request_code(self, email: str) -> str:
        with patch("app.accounts.email.send_reset_code") as sender:
            request_password_reset(self.db, email)
        if not sender.called:
            return ""
        return sender.call_args[0][1]

    # --- change_password -------------------------------------------------

    def test_change_password_requires_correct_current_password(self):
        with self.assertRaises(HTTPException) as ctx:
            change_password(self.db, self.local_user, "wrong-password", "new-password-123")
        self.assertEqual(ctx.exception.status_code, 401)

    def test_change_password_succeeds_with_correct_current_password(self):
        change_password(self.db, self.local_user, "original-password", "new-password-123")
        self.db.refresh(self.local_user)
        self.assertTrue(verify_password("new-password-123", self.local_user.password_hash))

    def test_google_only_account_can_set_a_password_without_current(self):
        change_password(self.db, self.google_user, None, "new-password-123")
        self.db.refresh(self.google_user)
        self.assertTrue(verify_password("new-password-123", self.google_user.password_hash))

    def test_change_password_rejects_short_password(self):
        with self.assertRaises(HTTPException) as ctx:
            change_password(self.db, self.local_user, "original-password", "short")
        self.assertEqual(ctx.exception.status_code, 422)

    # --- request_password_reset / confirm_password_reset -----------------

    def test_unknown_email_is_quiet_and_sends_nothing(self):
        with patch("app.accounts.email.send_reset_code") as sender:
            request_password_reset(self.db, "nobody@example.test")
        sender.assert_not_called()

    def test_request_then_confirm_changes_the_password(self):
        code = self._request_code(self.local_user.email)
        self.assertRegex(code, r"^\d{6}$")
        confirm_password_reset(self.db, self.local_user.email, code, "reset-password-123")
        self.db.refresh(self.local_user)
        self.assertTrue(verify_password("reset-password-123", self.local_user.password_hash))

    def test_code_cannot_be_used_twice(self):
        code = self._request_code(self.local_user.email)
        confirm_password_reset(self.db, self.local_user.email, code, "reset-password-123")
        with self.assertRaises(HTTPException) as ctx:
            confirm_password_reset(self.db, self.local_user.email, code, "another-password-1")
        self.assertEqual(ctx.exception.status_code, 400)

    def test_wrong_code_is_rejected_and_counts_as_an_attempt(self):
        self._request_code(self.local_user.email)
        with self.assertRaises(HTTPException) as ctx:
            confirm_password_reset(self.db, self.local_user.email, "000000", "reset-password-123")
        self.assertEqual(ctx.exception.status_code, 400)
        row = self.db.query(PasswordResetCode).filter(PasswordResetCode.user_id == self.local_user.id).one()
        self.assertEqual(row.attempts, 1)

    def test_too_many_wrong_attempts_blocks_the_correct_code_too(self):
        code = self._request_code(self.local_user.email)
        for _ in range(RESET_CODE_MAX_ATTEMPTS):
            with self.assertRaises(HTTPException):
                confirm_password_reset(self.db, self.local_user.email, "000000", "reset-password-123")
        with self.assertRaises(HTTPException) as ctx:
            confirm_password_reset(self.db, self.local_user.email, code, "reset-password-123")
        self.assertEqual(ctx.exception.status_code, 400)

    def test_expired_code_is_rejected(self):
        code = self._request_code(self.local_user.email)
        row = self.db.query(PasswordResetCode).filter(PasswordResetCode.user_id == self.local_user.id).one()
        row.expires_at = _now() - timedelta(seconds=1)
        self.db.commit()
        with self.assertRaises(HTTPException) as ctx:
            confirm_password_reset(self.db, self.local_user.email, code, "reset-password-123")
        self.assertEqual(ctx.exception.status_code, 400)

    def test_requesting_again_invalidates_the_previous_code(self):
        first = self._request_code(self.local_user.email)
        row = self.db.query(PasswordResetCode).filter(PasswordResetCode.user_id == self.local_user.id).one()
        row.created_at = _now() - timedelta(minutes=5)
        self.db.commit()
        second = self._request_code(self.local_user.email)
        self.assertNotEqual(first, second)
        with self.assertRaises(HTTPException):
            confirm_password_reset(self.db, self.local_user.email, first, "reset-password-123")
        confirm_password_reset(self.db, self.local_user.email, second, "reset-password-123")

    def test_rapid_second_request_is_rate_limited(self):
        self._request_code(self.local_user.email)
        with self.assertRaises(HTTPException) as ctx:
            request_password_reset(self.db, self.local_user.email)
        self.assertEqual(ctx.exception.status_code, 429)

    def test_code_only_resets_the_requesting_users_password(self):
        code = self._request_code(self.local_user.email)
        with self.assertRaises(HTTPException):
            confirm_password_reset(self.db, self.google_user.email, code, "reset-password-123")


if __name__ == "__main__":
    unittest.main()
