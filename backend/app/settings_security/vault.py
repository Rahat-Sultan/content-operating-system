"""
The Settings vault: a second password, separate from the login password, that gates
API keys and Platforms. Unlocking is per browser session and lasts 15 minutes, then the
session must unlock again — a long-lived login cookie does not keep the vault open.
"""
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi import Cookie, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.accounts.models import User, VaultUnlock
from app.accounts.service import COOKIE_NAME, current_user
from app.db import get_db
from app.settings_security.crypto import MIN_PASSWORD_LENGTH, hash_password, token_hash, verify_password

UNLOCK_LIFETIME = timedelta(minutes=15)
LOCKED_DETAIL = "Settings are locked. Enter your settings password to continue."
MAX_UNLOCK_ATTEMPTS = 5
UNLOCK_COOLDOWN = timedelta(minutes=15)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def vault_status(db: Session, user: User, session_token: str | None) -> dict:
    configured = user.vault_password_hash is not None
    unlocked_until = None
    if configured and session_token:
        row = db.query(VaultUnlock).filter(VaultUnlock.session_token_hash == token_hash(session_token)).first()
        if row and row.expires_at > _now():
            unlocked_until = row.expires_at
    return {"configured": configured, "unlocked": unlocked_until is not None, "unlocked_until": unlocked_until}


def set_vault_password(db: Session, user: User, current_password: str | None, new_password: str) -> None:
    if len(new_password) < MIN_PASSWORD_LENGTH:
        raise HTTPException(status_code=422, detail=f"Use at least {MIN_PASSWORD_LENGTH} characters.")
    if user.vault_password_hash is not None:
        if not current_password or not verify_password(current_password, user.vault_password_hash):
            raise HTTPException(status_code=401, detail="Current settings password is wrong.")
    db.query(User).filter(User.id == user.id).update({User.vault_password_hash: hash_password(new_password)})
    db.commit()


def unlock_vault(db: Session, user: User, session_token: str | None, password: str) -> datetime:
    if not session_token:
        raise HTTPException(status_code=401, detail="Please log in.")
    if user.vault_password_hash is None:
        raise HTTPException(status_code=403, detail="Set a settings password first.")
    if user.vault_locked_until and user.vault_locked_until > _now():
        raise HTTPException(status_code=423, detail="Too many wrong attempts. Try again later.")
    if not verify_password(password, user.vault_password_hash):
        db.execute(text(
            "UPDATE users SET vault_failed_attempts = vault_failed_attempts + 1, "
            "vault_locked_until = CASE WHEN vault_failed_attempts + 1 >= :max THEN now() + :lock ELSE vault_locked_until END "
            "WHERE id = :id"
        ), {"max": MAX_UNLOCK_ATTEMPTS, "lock": UNLOCK_COOLDOWN, "id": user.id})
        db.commit()
        raise HTTPException(status_code=401, detail="Wrong settings password.")
    db.execute(text("UPDATE users SET vault_failed_attempts = 0, vault_locked_until = NULL WHERE id = :id"), {"id": user.id})

    expires_at = _now() + UNLOCK_LIFETIME
    th = token_hash(session_token)
    existing = db.query(VaultUnlock).filter(VaultUnlock.session_token_hash == th).first()
    if existing:
        existing.expires_at = expires_at
    else:
        db.add(VaultUnlock(session_token_hash=th, user_id=user.id, expires_at=expires_at))
    db.commit()
    return expires_at


def lock_vault(db: Session, session_token: str | None) -> None:
    if session_token:
        db.query(VaultUnlock).filter(VaultUnlock.session_token_hash == token_hash(session_token)).delete()
        db.commit()


def require_vault_unlocked(
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
    cos_session: str | None = Cookie(default=None, alias=COOKIE_NAME),
) -> User:
    """Dependency for every API keys / Platforms route. Raises before the route body runs."""
    if user.vault_password_hash is None:
        raise HTTPException(status_code=403, detail="Set a settings password first.")
    if not cos_session:
        raise HTTPException(status_code=401, detail="Please log in.")
    row = db.query(VaultUnlock).filter(VaultUnlock.session_token_hash == token_hash(cos_session)).first()
    if row is None or row.expires_at <= _now():
        raise HTTPException(status_code=status.HTTP_423_LOCKED, detail=LOCKED_DETAIL)
    return user
