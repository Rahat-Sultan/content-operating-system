"""
Accounts and login: registration, password checks, lockout, session cookie, logout, expiry.
Database tests run in one rolled-back transaction.
"""
import os
import unittest
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "../backend/.env"))

from fastapi import HTTPException, Response
from sqlalchemy.orm import Session

from app.accounts import service
from app.accounts.models import User, UserSession
from app.db import engine
from app.settings_security.crypto import token_hash


class Isolated(unittest.TestCase):
    def setUp(self):
        self.connection = engine.connect()
        self.outer = self.connection.begin()
        self.db = Session(bind=self.connection, join_transaction_mode="create_savepoint")
        self.email = f"user-{uuid4().hex[:8]}@example.test"

    def tearDown(self):
        self.db.close()
        self.outer.rollback()
        self.connection.close()


class TestRegisterAndLogin(Isolated):
    def test_register_then_login(self):
        service.register(self.db, self.email, "a-long-enough-password", "Ann")
        response = Response()
        user = service.login(self.db, self.email, "a-long-enough-password", response)
        self.assertEqual(user.email, self.email)
        self.assertIn("HttpOnly", response.headers["set-cookie"])
        self.assertNotIn("max-age", response.headers["set-cookie"].lower())

    def test_short_password_refused(self):
        with self.assertRaises(HTTPException) as ctx:
            service.register(self.db, self.email, "short", None)
        self.assertEqual(ctx.exception.status_code, 422)

    def test_duplicate_email_refused(self):
        service.register(self.db, self.email, "a-long-enough-password", None)
        with self.assertRaises(HTTPException) as ctx:
            service.register(self.db, self.email, "another-long-password", None)
        self.assertEqual(ctx.exception.status_code, 409)

    def test_wrong_password_and_unknown_email_give_the_same_answer(self):
        service.register(self.db, self.email, "a-long-enough-password", None)
        with self.assertRaises(HTTPException) as wrong:
            service.login(self.db, self.email, "not-the-password", Response())
        with self.assertRaises(HTTPException) as unknown:
            service.login(self.db, f"nobody-{uuid4().hex}@example.test", "x", Response())
        self.assertEqual((wrong.exception.status_code, wrong.exception.detail),
                         (unknown.exception.status_code, unknown.exception.detail))

    def test_five_wrong_attempts_lock_the_account(self):
        service.register(self.db, self.email, "a-long-enough-password", None)
        for _ in range(service.MAX_FAILED_ATTEMPTS):
            with self.assertRaises(HTTPException):
                service.login(self.db, self.email, "wrong-password-here", Response())
        with self.assertRaises(HTTPException) as ctx:
            service.login(self.db, self.email, "a-long-enough-password", Response())
        self.assertEqual(ctx.exception.status_code, 423)


class TestSessions(Isolated):
    def _login(self):
        service.register(self.db, self.email, "a-long-enough-password", None)
        response = Response()
        user = service.login(self.db, self.email, "a-long-enough-password", response)
        token = response.headers["set-cookie"].split(";")[0].split("=", 1)[1]
        return user, token

    def test_current_user_needs_a_valid_session(self):
        user, token = self._login()
        self.assertEqual(service.current_user(self.db, token).id, user.id)
        with self.assertRaises(HTTPException) as ctx:
            service.current_user(self.db, None)
        self.assertEqual(ctx.exception.status_code, 401)

    def test_logout_ends_the_session(self):
        _, token = self._login()
        service.logout(self.db, token, Response())
        with self.assertRaises(HTTPException) as ctx:
            service.current_user(self.db, token)
        self.assertEqual(ctx.exception.status_code, 401)

    def test_expired_session_is_refused(self):
        user, token = self._login()
        row = self.db.query(UserSession).filter(UserSession.token_hash == token_hash(token)).one()
        row.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        self.db.commit()
        with self.assertRaises(HTTPException) as ctx:
            service.current_user(self.db, token)
        self.assertEqual(ctx.exception.status_code, 401)


if __name__ == "__main__":
    unittest.main()
