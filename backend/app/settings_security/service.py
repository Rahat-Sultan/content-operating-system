"""
API keys of one account. Keys are encrypted (Fernet). Only a count of characters is shown.
Account login is the only gate; there is no separate Settings password.
"""
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.config import settings
from app.settings_security.crypto import EncryptionKeyMissing, decrypt, encrypt
from app.settings_security.models import SecretValue

# API keys the Settings page manages: name -> (provider label, attribute on settings)
MANAGED_KEYS = {
    "OPENROUTER_API_KEY": ("OpenRouter (LLM gateway)", "openrouter_api_key"),
    "BUFFER_ACCESS_TOKEN": ("Buffer (publishing and analytics)", "buffer_access_token"),
}


def list_keys(db: Session, owner_id: UUID) -> list[dict]:
    rows = {r.name: r for r in db.query(SecretValue).filter(SecretValue.owner_id == owner_id).all()}
    out = []
    for name, (label, attr) in MANAGED_KEYS.items():
        row = rows.get(name)
        # A key from .env is the installation default. It is shown to the owner of the installation only.
        env_value = getattr(settings, attr, "") or ""
        out.append({
            "name": name,
            "label": label,
            "saved_in_app": row is not None,
            "last4": row.last4 if row else None,
            "from_env": row is None and bool(env_value),
            "is_set": row is not None or bool(env_value),
            "updated_at": row.updated_at.isoformat() if row else None,
        })
    return out


def set_key(db: Session, owner_id: UUID, name: str, value: str) -> None:
    if name not in MANAGED_KEYS:
        raise HTTPException(status_code=404, detail=f"Unknown key '{name}'.")
    value = value.strip()
    if len(value) < 8 or len(value) > 300 or any(c.isspace() for c in value):
        raise HTTPException(status_code=422, detail="A key is 8 to 300 characters with no spaces.")
    try:
        ciphertext = encrypt(value)
    except EncryptionKeyMissing as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    stmt = pg_insert(SecretValue).values(owner_id=owner_id, name=name, ciphertext=ciphertext,
                                         last4=value[-4:], updated_at=now)
    stmt = stmt.on_conflict_do_update(index_elements=[SecretValue.owner_id, SecretValue.name],
                                      set_={"ciphertext": ciphertext, "last4": value[-4:], "updated_at": now})
    db.execute(stmt)
    db.commit()


def delete_key(db: Session, owner_id: UUID, name: str) -> None:
    if name not in MANAGED_KEYS:
        raise HTTPException(status_code=404, detail=f"Unknown key '{name}'.")
    db.query(SecretValue).filter(SecretValue.owner_id == owner_id, SecretValue.name == name).delete()
    db.commit()


def key_for(db: Session, owner_id: UUID | None, name: str) -> str | None:
    """
    The key an account should use: its own saved key, else the installation default in .env.
    Returns None when neither exists.
    """
    if owner_id is not None:
        row = db.query(SecretValue).filter(SecretValue.owner_id == owner_id, SecretValue.name == name).first()
        if row is not None:
            return decrypt(row.ciphertext)
    attr = MANAGED_KEYS[name][1]
    return getattr(settings, attr, None) or None
