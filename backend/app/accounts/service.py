"""
Accounts and login. Local accounts (email + password) are the default.
Each login is a server-side session; the browser cookie has no expiry, so it ends
when the browser session ends. The server also expires sessions after 8 hours.
"""
import re
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import Cookie, Depends, HTTPException, Response, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.accounts.models import User, UserSession
from app.db import get_db
from app.settings_security.crypto import (
    MIN_PASSWORD_LENGTH, hash_password, new_session_token, token_hash, verify_password,
)

COOKIE_NAME = "cos_session"
SESSION_LIFETIME = timedelta(hours=8)
MAX_FAILED_ATTEMPTS = 5
LOCKOUT = timedelta(minutes=15)
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def normalize_email(email: str) -> str:
    email = (email or "").strip().lower()
    if not EMAIL_RE.match(email) or len(email) > 254:
        raise HTTPException(status_code=422, detail="Enter a valid email address.")
    return email


def register(db: Session, email: str, password: str, display_name: str | None) -> User:
    email = normalize_email(email)
    if len(password) < MIN_PASSWORD_LENGTH:
        raise HTTPException(status_code=422, detail=f"Use at least {MIN_PASSWORD_LENGTH} characters.")
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(status_code=409, detail="An account with this email already exists.")
    user = User(
        id=uuid.uuid4(),
        email=email,
        display_name=(display_name or "").strip() or email.split("@")[0],
        password_hash=hash_password(password),
        auth_provider="local",
    )
    db.add(user)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(status_code=409, detail="An account with this email already exists.")
    db.refresh(user)
    return user


def _start_session(db: Session, user: User, response: Response) -> None:
    token = new_session_token()
    db.query(UserSession).filter(UserSession.expires_at <= _now()).delete()
    db.add(UserSession(token_hash=token_hash(token), user_id=user.id, expires_at=_now() + SESSION_LIFETIME))
    db.commit()
    # No max_age: the browser discards the cookie when the browser session ends.
    response.set_cookie(COOKIE_NAME, token, httponly=True, samesite="strict", path="/api")


def login(db: Session, email: str, password: str, response: Response) -> User:
    email = normalize_email(email)
    user = db.query(User).filter(User.email == email).first()
    # Same answer whether the email exists or not.
    if user is None or user.password_hash is None:
        raise HTTPException(status_code=401, detail="Wrong email or password.")
    if user.locked_until and user.locked_until > _now():
        raise HTTPException(status_code=423, detail="Too many wrong attempts. Try again later.")
    if not verify_password(password, user.password_hash):
        db.execute(text(
            "UPDATE users SET failed_attempts = failed_attempts + 1, "
            "locked_until = CASE WHEN failed_attempts + 1 >= :max THEN now() + :lock ELSE locked_until END "
            "WHERE id = :id"
        ), {"max": MAX_FAILED_ATTEMPTS, "lock": LOCKOUT, "id": user.id})
        db.commit()
        raise HTTPException(status_code=401, detail="Wrong email or password.")
    db.execute(text("UPDATE users SET failed_attempts = 0, locked_until = NULL WHERE id = :id"), {"id": user.id})
    db.commit()
    _start_session(db, user, response)
    return user


def start_session_for(db: Session, user: User, response: Response) -> None:
    """Used by the Google sign-in callback after the provider has confirmed the person."""
    _start_session(db, user, response)


def logout(db: Session, cookie: str | None, response: Response) -> None:
    if cookie:
        db.query(UserSession).filter(UserSession.token_hash == token_hash(cookie)).delete()
        db.commit()
    response.delete_cookie(COOKIE_NAME, path="/api")


def current_user(
    db: Session = Depends(get_db),
    cos_session: str | None = Cookie(default=None, alias=COOKIE_NAME),
) -> User:
    """Every app route depends on this. No valid session means 401."""
    if not cos_session:
        raise HTTPException(status_code=401, detail="Please log in.")
    row = db.query(UserSession).filter(UserSession.token_hash == token_hash(cos_session)).first()
    if row is None or row.expires_at <= _now():
        raise HTTPException(status_code=401, detail="Your session has ended. Please log in again.")
    user = db.query(User).filter(User.id == row.user_id).first()
    if user is None:
        raise HTTPException(status_code=401, detail="Please log in.")
    return user
