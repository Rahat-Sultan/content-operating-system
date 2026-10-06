"""
Settings access: password setup and login, sessions that end with the browser session,
and API keys stored encrypted. Only the Settings routes depend on this module.
"""
from datetime import datetime, timedelta, timezone

from fastapi import Cookie, HTTPException, Response, status
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.config import Settings, settings
from app.settings_security.crypto import (
    MIN_PASSWORD_LENGTH, decrypt, encrypt, hash_password, new_session_token,
    token_hash, verify_password, EncryptionKeyMissing,
)
from app.settings_security.models import SecretValue, SettingsAuth, SettingsSession

COOKIE_NAME = "cos_settings_session"
SESSION_LIFETIME = timedelta(hours=8)     # server-side limit, on top of the browser-session cookie
MAX_FAILED_ATTEMPTS = 5
LOCKOUT = timedelta(minutes=15)

# API keys the Settings page manages: name -> (provider label, attribute on settings)
MANAGED_KEYS = {
    "OPENROUTER_API_KEY": ("OpenRouter (LLM gateway)", "openrouter_api_key"),
    "BUFFER_ACCESS_TOKEN": ("Buffer (publishing and analytics)", "buffer_access_token"),
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ---------- password and sessions ----------

def auth_status(db: Session, cookie: str | None) -> dict:
    row = db.query(SettingsAuth).filter(SettingsAuth.id == 1).first()
    unlocked = False
    if cookie:
        s = db.query(SettingsSession).filter(SettingsSession.token_hash == token_hash(cookie)).first()
        unlocked = bool(s and s.expires_at > _now())
    locked_until = row.locked_until.isoformat() if row and row.locked_until and row.locked_until > _now() else None
    return {"configured": row is not None, "unlocked": unlocked, "locked_until": locked_until}


def setup_password(db: Session, password: str) -> None:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise HTTPException(status_code=422, detail=f"Use at least {MIN_PASSWORD_LENGTH} characters.")
    stmt = (
        pg_insert(SettingsAuth)
        .values(id=1, password_hash=hash_password(password))
        .on_conflict_do_nothing()
        .returning(SettingsAuth.id)
    )
    inserted = db.execute(stmt).first()
    db.commit()
    if inserted is None:
        raise HTTPException(status_code=409, detail="The Settings password is already set.")


def login(db: Session, password: str, response: Response) -> None:
    row = db.query(SettingsAuth).filter(SettingsAuth.id == 1).first()
    if row is None:
        raise HTTPException(status_code=409, detail="Set a Settings password first.")
    if row.locked_until and row.locked_until > _now():
        raise HTTPException(status_code=423, detail="Too many wrong attempts. Try again later.")

    if not verify_password(password, row.password_hash):
        # One atomic statement: count the failure and lock when the limit is reached.
        db.execute(text(
            "UPDATE settings_auth SET failed_attempts = failed_attempts + 1, "
            "locked_until = CASE WHEN failed_attempts + 1 >= :max THEN now() + :lock ELSE locked_until END "
            "WHERE id = 1"
        ), {"max": MAX_FAILED_ATTEMPTS, "lock": LOCKOUT})
        db.commit()
        raise HTTPException(status_code=401, detail="Wrong password.")

    db.execute(text("UPDATE settings_auth SET failed_attempts = 0, locked_until = NULL WHERE id = 1"))
    db.query(SettingsSession).filter(SettingsSession.expires_at <= _now()).delete()
    token = new_session_token()
    db.add(SettingsSession(token_hash=token_hash(token), expires_at=_now() + SESSION_LIFETIME))
    db.commit()
    # No max_age: the browser discards the cookie when the browser session ends.
    response.set_cookie(COOKIE_NAME, token, httponly=True, samesite="strict", path="/api/settings")


def logout(db: Session, cookie: str | None, response: Response) -> None:
    if cookie:
        db.query(SettingsSession).filter(SettingsSession.token_hash == token_hash(cookie)).delete()
        db.commit()
    response.delete_cookie(COOKIE_NAME, path="/api/settings")


def require_session(db: Session, cookie: str | None) -> None:
    if not cookie:
        raise HTTPException(status_code=401, detail="Settings are locked. Enter the Settings password.")
    s = db.query(SettingsSession).filter(SettingsSession.token_hash == token_hash(cookie)).first()
    if s is None or s.expires_at <= _now():
        raise HTTPException(status_code=401, detail="Your Settings session has ended. Enter the password again.")


# ---------- API keys ----------

def list_keys(db: Session) -> list[dict]:
    rows = {r.name: r for r in db.query(SecretValue).all()}
    out = []
    for name, (label, attr) in MANAGED_KEYS.items():
        row = rows.get(name)
        env_value = getattr(Settings(), attr, "") or ""
        out.append({
            "name": name,
            "label": label,
            "saved_in_app": row is not None,
            "last4": row.last4 if row else (env_value[-4:] if env_value else None),
            "from_env": row is None and bool(env_value),
            "is_set": row is not None or bool(env_value),
            "updated_at": row.updated_at.isoformat() if row else None,
        })
    return out


def set_key(db: Session, name: str, value: str) -> None:
    if name not in MANAGED_KEYS:
        raise HTTPException(status_code=404, detail=f"Unknown key '{name}'.")
    value = value.strip()
    if len(value) < 8 or len(value) > 300 or any(c.isspace() for c in value):
        raise HTTPException(status_code=422, detail="A key is 8 to 300 characters with no spaces.")
    try:
        ciphertext = encrypt(value)
    except EncryptionKeyMissing as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    stmt = pg_insert(SecretValue).values(name=name, ciphertext=ciphertext, last4=value[-4:], updated_at=_now())
    stmt = stmt.on_conflict_do_update(index_elements=[SecretValue.name],
                                      set_={"ciphertext": ciphertext, "last4": value[-4:], "updated_at": _now()})
    db.execute(stmt)
    db.commit()
    apply_saved_keys(db)


def delete_key(db: Session, name: str) -> None:
    if name not in MANAGED_KEYS:
        raise HTTPException(status_code=404, detail=f"Unknown key '{name}'.")
    db.query(SecretValue).filter(SecretValue.name == name).delete()
    db.commit()
    # Fall back to the value in .env, if there is one.
    attr = MANAGED_KEYS[name][1]
    setattr(settings, attr, getattr(Settings(), attr, ""))
    _reset_provider_caches()


def apply_saved_keys(db: Session) -> None:
    """Loads keys saved in the app into the running settings object. Called at startup and each worker loop."""
    rows = db.query(SecretValue).all()
    for row in rows:
        attr = MANAGED_KEYS.get(row.name, (None, None))[1]
        if not attr:
            continue
        value = decrypt(row.ciphertext)
        if value and getattr(settings, attr, None) != value:
            setattr(settings, attr, value)
            _reset_provider_caches()


def _reset_provider_caches() -> None:
    # Providers cache a token when first created; drop them so the new key is used.
    try:
        import app.analytics.factory as analytics_factory
        analytics_factory._default_buffer_analytics = None
    except Exception:
        pass
