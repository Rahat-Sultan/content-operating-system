"""
Which account a piece of work runs for. Set by the request, or by the worker per job.
Providers read keys through active_key(), so every call uses the owner's own key.
Keys are read from the database on each call, so a key changed in Settings applies at once,
in the API process and in the worker alike.
"""
from contextvars import ContextVar
from uuid import UUID

_owner: ContextVar[UUID | None] = ContextVar("owner_id", default=None)


def set_current_owner(owner_id: UUID | None):
    return _owner.set(owner_id)


def reset_current_owner(token) -> None:
    _owner.reset(token)


def current_owner() -> UUID | None:
    return _owner.get()


def active_key(name: str) -> str | None:
    """The key for the account in context (its own, else the installation default in .env)."""
    from app.db import SessionLocal
    from app.settings_security.service import key_for
    db = SessionLocal()
    try:
        return key_for(db, _owner.get(), name)
    finally:
        db.close()
