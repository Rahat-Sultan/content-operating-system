"""
The Settings vault: a second password gating API keys and Platforms, unlocked per
browser session for 15 minutes. Runs inside one transaction on a single connection,
rolled back in tearDown, so the real contentos_dev data is untouched.
"""
import os
import unittest
from datetime import timedelta
from uuid import uuid4

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "../backend/.env"))

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.db import engine
from app.accounts.models import User, UserSession, VaultUnlock
from app.accounts.service import new_session_token, token_hash
from app.settings_security.vault import (
    MAX_UNLOCK_ATTEMPTS,
    UNLOCK_LIFETIME,
    _now,
    lock_vault,
    require_vault_unlocked,
    set_vault_password,
    unlock_vault,
    vault_status,
)


class SettingsVaultTest(unittest.TestCase):
    def setUp(self):
        self.connection = engine.connect()
        self.outer = self.connection.begin()
        self.db = Session(bind=self.connection, join_transaction_mode="create_savepoint")
        self.user = User(id=uuid4(), email=f"vault-{uuid4()}@example.test", display_name="Vault", auth_provider="local")
        self.db.add(self.user)
        self.db.flush()
        self.token = new_session_token()
        self.db.add(UserSession(token_hash=token_hash(self.token), user_id=self.user.id, expires_at=_now() + timedelta(hours=8)))
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.outer.rollback()
        self.connection.close()

    def test_not_configured_until_a_vault_password_is_set(self):
        status = vault_status(self.db, self.user, self.token)
        self.assertFalse(status["configured"])
        self.assertFalse(status["unlocked"])

    def test_require_unlocked_refuses_before_a_vault_password_exists(self):
        with self.assertRaises(HTTPException) as ctx:
            require_vault_unlocked(self.db, self.user, self.token)
        self.assertEqual(ctx.exception.status_code, 403)

    def test_first_time_set_needs_no_current_password(self):
        set_vault_password(self.db, self.user, None, "vault-password-123")
        self.db.refresh(self.user)
        self.assertIsNotNone(self.user.vault_password_hash)

    def test_changing_it_requires_the_current_vault_password(self):
        set_vault_password(self.db, self.user, None, "vault-password-123")
        with self.assertRaises(HTTPException) as ctx:
            set_vault_password(self.db, self.user, "wrong", "vault-password-456")
        self.assertEqual(ctx.exception.status_code, 401)
        set_vault_password(self.db, self.user, "vault-password-123", "vault-password-456")

    def test_unlock_with_wrong_password_is_refused(self):
        set_vault_password(self.db, self.user, None, "vault-password-123")
        with self.assertRaises(HTTPException) as ctx:
            unlock_vault(self.db, self.user, self.token, "nope")
        self.assertEqual(ctx.exception.status_code, 401)

    def test_too_many_wrong_attempts_locks_out_even_the_correct_password(self):
        set_vault_password(self.db, self.user, None, "vault-password-123")
        for _ in range(MAX_UNLOCK_ATTEMPTS):
            with self.assertRaises(HTTPException):
                unlock_vault(self.db, self.user, self.token, "nope")
        self.db.refresh(self.user)
        with self.assertRaises(HTTPException) as ctx:
            unlock_vault(self.db, self.user, self.token, "vault-password-123")
        self.assertEqual(ctx.exception.status_code, 423)

    def test_a_correct_unlock_resets_the_failed_count(self):
        set_vault_password(self.db, self.user, None, "vault-password-123")
        with self.assertRaises(HTTPException):
            unlock_vault(self.db, self.user, self.token, "nope")
        unlock_vault(self.db, self.user, self.token, "vault-password-123")
        self.db.refresh(self.user)
        self.assertEqual(self.user.vault_failed_attempts, 0)
        self.assertIsNone(self.user.vault_locked_until)

    def test_unlock_with_correct_password_lets_the_dependency_pass(self):
        set_vault_password(self.db, self.user, None, "vault-password-123")
        expires_at = unlock_vault(self.db, self.user, self.token, "vault-password-123")
        self.assertAlmostEqual(expires_at, _now() + UNLOCK_LIFETIME, delta=timedelta(seconds=5))
        user = require_vault_unlocked(self.db, self.user, self.token)
        self.assertEqual(user.id, self.user.id)
        status = vault_status(self.db, self.user, self.token)
        self.assertTrue(status["unlocked"])

    def test_expired_unlock_locks_again(self):
        set_vault_password(self.db, self.user, None, "vault-password-123")
        unlock_vault(self.db, self.user, self.token, "vault-password-123")
        row = self.db.query(VaultUnlock).filter(VaultUnlock.session_token_hash == token_hash(self.token)).one()
        row.expires_at = _now() - timedelta(seconds=1)
        self.db.commit()
        with self.assertRaises(HTTPException) as ctx:
            require_vault_unlocked(self.db, self.user, self.token)
        self.assertEqual(ctx.exception.status_code, 423)

    def test_lock_now_relocks_immediately(self):
        set_vault_password(self.db, self.user, None, "vault-password-123")
        unlock_vault(self.db, self.user, self.token, "vault-password-123")
        lock_vault(self.db, self.token)
        with self.assertRaises(HTTPException) as ctx:
            require_vault_unlocked(self.db, self.user, self.token)
        self.assertEqual(ctx.exception.status_code, 423)

    def test_unlock_is_scoped_to_the_session_that_unlocked_it(self):
        set_vault_password(self.db, self.user, None, "vault-password-123")
        unlock_vault(self.db, self.user, self.token, "vault-password-123")

        other_token = new_session_token()
        self.db.add(UserSession(token_hash=token_hash(other_token), user_id=self.user.id, expires_at=_now() + timedelta(hours=8)))
        self.db.commit()

        with self.assertRaises(HTTPException) as ctx:
            require_vault_unlocked(self.db, self.user, other_token)
        self.assertEqual(ctx.exception.status_code, 423)

    def test_unlocking_twice_extends_rather_than_duplicates(self):
        set_vault_password(self.db, self.user, None, "vault-password-123")
        unlock_vault(self.db, self.user, self.token, "vault-password-123")
        unlock_vault(self.db, self.user, self.token, "vault-password-123")
        rows = self.db.query(VaultUnlock).filter(VaultUnlock.session_token_hash == token_hash(self.token)).all()
        self.assertEqual(len(rows), 1)


if __name__ == "__main__":
    unittest.main()
