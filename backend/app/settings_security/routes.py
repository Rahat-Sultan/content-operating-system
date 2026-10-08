from uuid import UUID

from fastapi import APIRouter, Cookie, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.accounts.models import User
from app.accounts.service import COOKIE_NAME, current_user
from app.db import get_db
from app.settings_security import service, vault

keys_router = APIRouter(prefix="/settings/keys", tags=["settings"])
vault_router = APIRouter(prefix="/settings/vault", tags=["settings"])


class KeyIn(BaseModel):
    value: str = Field(min_length=1, max_length=400)


@keys_router.get("", dependencies=[Depends(vault.require_vault_unlocked)])
def keys(db: Session = Depends(get_db), user: User = Depends(current_user)):
    return service.list_keys(db, user.id)


@keys_router.put("/{name}", dependencies=[Depends(vault.require_vault_unlocked)])
def save_key(name: str, body: KeyIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    service.set_key(db, user.id, name, body.value)
    return {"ok": True}


@keys_router.delete("/{name}", dependencies=[Depends(vault.require_vault_unlocked)])
def remove_key(name: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    service.delete_key(db, user.id, name)
    return {"ok": True}


class SetVaultPasswordIn(BaseModel):
    current_password: str | None = Field(default=None, max_length=256)
    new_password: str = Field(min_length=1, max_length=256)


class UnlockVaultIn(BaseModel):
    password: str = Field(min_length=1, max_length=256)


@vault_router.get("/status")
def vault_status(
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
    cos_session: str | None = Cookie(default=None, alias=COOKIE_NAME),
):
    return vault.vault_status(db, user, cos_session)


@vault_router.post("/set")
def set_vault_password(
    body: SetVaultPasswordIn,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
    cos_session: str | None = Cookie(default=None, alias=COOKIE_NAME),
):
    first_time = user.vault_password_hash is None
    vault.set_vault_password(db, user, body.current_password, body.new_password)
    unlocked_until = None
    if first_time:
        # Typing the new password twice already proves it; no need to ask a third time.
        unlocked_until = vault.unlock_vault(db, user, cos_session, body.new_password)
    return {"ok": True, "unlocked_until": unlocked_until}


@vault_router.post("/unlock")
def unlock_vault(
    body: UnlockVaultIn,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
    cos_session: str | None = Cookie(default=None, alias=COOKIE_NAME),
):
    unlocked_until = vault.unlock_vault(db, user, cos_session, body.password)
    return {"unlocked_until": unlocked_until}


@vault_router.post("/lock")
def lock_vault(
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
    cos_session: str | None = Cookie(default=None, alias=COOKIE_NAME),
):
    vault.lock_vault(db, cos_session)
    return {"ok": True}
