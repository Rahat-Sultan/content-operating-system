"""
Accounts and login. Local accounts (email + password) are the default.
Each login is a server-side session; the browser cookie has no expiry, so it ends
when the browser session ends. The server also expires sessions after 8 hours.
"""
import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import Cookie, Depends, HTTPException, Response, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.accounts.models import PasswordResetCode, User, UserSession
from app.config import settings
from app.db import get_db
from app.settings_security.crypto import (
    MIN_PASSWORD_LENGTH, hash_password, new_session_token, token_hash, verify_password,
)

COOKIE_NAME = "cos_session"
# The cookie is marked Secure outside local development, so it is never sent over plain
# HTTP once the app is deployed. Local dev stays on http://localhost, where Secure
# would block the cookie entirely.
COOKIE_SECURE = settings.environment != "development"
SESSION_LIFETIME = timedelta(hours=8)
MAX_FAILED_ATTEMPTS = 5
LOCKOUT = timedelta(minutes=15)
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

RESET_CODE_LIFETIME = timedelta(minutes=10)
RESET_CODE_COOLDOWN = timedelta(seconds=60)
RESET_CODE_MAX_ATTEMPTS = 5
GENERIC_RESET_ERROR = "That code is invalid or has expired. Request a new one."


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
    # New accounts start with the default sources. A failure here must not block sign-up.
    try:
        from app.sources.catalog import seed_default_sources
        seed_default_sources(db, user.id)
    except Exception:
        db.rollback()
    return user


def _start_session(db: Session, user: User, response: Response) -> None:
    token = new_session_token()
    db.query(UserSession).filter(UserSession.expires_at <= _now()).delete()
    db.add(UserSession(token_hash=token_hash(token), user_id=user.id, expires_at=_now() + SESSION_LIFETIME))
    db.commit()
    # No max_age: the browser discards the cookie when the browser session ends.
    response.set_cookie(COOKIE_NAME, token, httponly=True, samesite="strict", secure=COOKIE_SECURE, path="/api")


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


def change_password(db: Session, user: User, current_password: str | None, new_password: str) -> None:
    """
    Sets a new password. A local account must give its current password. A Google-only
    account (no password yet) may set one without, which is how it gains a local login.
    """
    if len(new_password) < MIN_PASSWORD_LENGTH:
        raise HTTPException(status_code=422, detail=f"Use at least {MIN_PASSWORD_LENGTH} characters.")
    if user.password_hash is not None:
        if not current_password or not verify_password(current_password, user.password_hash):
            raise HTTPException(status_code=401, detail="Current password is wrong.")
    db.query(User).filter(User.id == user.id).update({User.password_hash: hash_password(new_password)})
    db.commit()


def _generate_unique_reset_code(db: Session) -> tuple[str, str]:
    """A 6-digit code whose hash does not collide with any other currently active code."""
    for _ in range(20):
        code = f"{secrets.randbelow(1_000_000):06d}"
        code_hash = token_hash(code)
        collision = (
            db.query(PasswordResetCode)
            .filter(PasswordResetCode.code_hash == code_hash, PasswordResetCode.used_at.is_(None),
                    PasswordResetCode.expires_at > _now())
            .first()
        )
        if not collision:
            return code, code_hash
    raise HTTPException(status_code=500, detail="Could not generate a reset code. Try again.")


def request_password_reset(db: Session, email: str) -> None:
    """
    Always succeeds from the caller's point of view, whether or not the email is
    registered, so a response never reveals which emails have accounts.
    """
    email = normalize_email(email)
    user = db.query(User).filter(User.email == email).first()
    if user is None:
        return

    recent = (
        db.query(PasswordResetCode)
        .filter(PasswordResetCode.user_id == user.id)
        .order_by(PasswordResetCode.created_at.desc())
        .first()
    )
    if recent and recent.created_at > _now() - RESET_CODE_COOLDOWN:
        raise HTTPException(status_code=429, detail="A code was just sent. Wait a minute before requesting another.")

    # Only one active code per user: anything unused is invalidated by the new one.
    db.query(PasswordResetCode).filter(
        PasswordResetCode.user_id == user.id, PasswordResetCode.used_at.is_(None)
    ).update({PasswordResetCode.used_at: _now()}, synchronize_session=False)

    code, code_hash = _generate_unique_reset_code(db)
    db.add(PasswordResetCode(
        id=uuid.uuid4(), user_id=user.id, code_hash=code_hash,
        expires_at=_now() + RESET_CODE_LIFETIME,
    ))
    db.commit()

    from app.accounts.email import send_reset_code
    send_reset_code(user.email, code)


def _active_reset_code(db: Session, user: User) -> PasswordResetCode | None:
    return (
        db.query(PasswordResetCode)
        .filter(PasswordResetCode.user_id == user.id, PasswordResetCode.used_at.is_(None),
                PasswordResetCode.expires_at > _now())
        .order_by(PasswordResetCode.created_at.desc())
        .first()
    )


def verify_password_reset_code(db: Session, email: str, code: str) -> None:
    """
    Checks the code without consuming it, so the UI can reveal the new-password step only
    after a correct code. A wrong guess still counts against the attempt limit.
    """
    email = normalize_email(email)
    user = db.query(User).filter(User.email == email).first()
    if user is None:
        raise HTTPException(status_code=400, detail=GENERIC_RESET_ERROR)
    row = _active_reset_code(db, user)
    if row is None or row.attempts >= RESET_CODE_MAX_ATTEMPTS:
        raise HTTPException(status_code=400, detail=GENERIC_RESET_ERROR)
    if row.code_hash != token_hash((code or "").strip()):
        db.query(PasswordResetCode).filter(PasswordResetCode.id == row.id).update(
            {PasswordResetCode.attempts: PasswordResetCode.attempts + 1}
        )
        db.commit()
        raise HTTPException(status_code=400, detail=GENERIC_RESET_ERROR)


def confirm_password_reset(db: Session, email: str, code: str, new_password: str) -> None:
    email = normalize_email(email)
    if len(new_password) < MIN_PASSWORD_LENGTH:
        raise HTTPException(status_code=422, detail=f"Use at least {MIN_PASSWORD_LENGTH} characters.")
    user = db.query(User).filter(User.email == email).first()
    if user is None:
        raise HTTPException(status_code=400, detail=GENERIC_RESET_ERROR)

    row = _active_reset_code(db, user)
    if row is None:
        raise HTTPException(status_code=400, detail=GENERIC_RESET_ERROR)
    if row.attempts >= RESET_CODE_MAX_ATTEMPTS:
        raise HTTPException(status_code=400, detail=GENERIC_RESET_ERROR)
    if row.code_hash != token_hash((code or "").strip()):
        db.query(PasswordResetCode).filter(PasswordResetCode.id == row.id).update(
            {PasswordResetCode.attempts: PasswordResetCode.attempts + 1}
        )
        db.commit()
        raise HTTPException(status_code=400, detail=GENERIC_RESET_ERROR)

    # Atomic: only the first matching confirm can mark the code used and change the password.
    claimed = (
        db.query(PasswordResetCode)
        .filter(PasswordResetCode.id == row.id, PasswordResetCode.used_at.is_(None))
        .update({PasswordResetCode.used_at: _now()}, synchronize_session=False)
    )
    if claimed != 1:
        raise HTTPException(status_code=400, detail=GENERIC_RESET_ERROR)
    db.query(User).filter(User.id == user.id).update({
        User.password_hash: hash_password(new_password),
        User.failed_attempts: 0,
        User.locked_until: None,
    })
    db.commit()


def update_display_name(db: Session, user: User, display_name: str) -> None:
    display_name = (display_name or "").strip()
    if not display_name:
        raise HTTPException(status_code=422, detail="Name cannot be empty.")
    if len(display_name) > 80:
        raise HTTPException(status_code=422, detail="Use at most 80 characters.")
    db.query(User).filter(User.id == user.id).update({User.display_name: display_name})
    db.commit()
    db.refresh(user)
