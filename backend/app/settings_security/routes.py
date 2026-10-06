from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.accounts.models import User
from app.accounts.service import current_user
from app.db import get_db
from app.settings_security import service

keys_router = APIRouter(prefix="/settings/keys", tags=["settings"])


class KeyIn(BaseModel):
    value: str = Field(min_length=1, max_length=400)


@keys_router.get("")
def keys(db: Session = Depends(get_db), user: User = Depends(current_user)):
    return service.list_keys(db, user.id)


@keys_router.put("/{name}")
def save_key(name: str, body: KeyIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    service.set_key(db, user.id, name, body.value)
    return {"ok": True}


@keys_router.delete("/{name}")
def remove_key(name: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    service.delete_key(db, user.id, name)
    return {"ok": True}
