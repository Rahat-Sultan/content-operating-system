from fastapi import APIRouter, Cookie, Depends, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db import get_db
from app.settings_security import service
from app.settings_security.deps import settings_session
from app.settings_security.service import COOKIE_NAME

auth_router = APIRouter(prefix="/settings/auth", tags=["settings"])
keys_router = APIRouter(prefix="/settings/keys", tags=["settings"], dependencies=[Depends(settings_session)])


class PasswordIn(BaseModel):
    password: str = Field(min_length=1, max_length=256)


class KeyIn(BaseModel):
    value: str = Field(min_length=1, max_length=400)


@auth_router.get("/status")
def auth_state(db: Session = Depends(get_db), cos_settings_session: str | None = Cookie(default=None, alias=COOKIE_NAME)):
    return service.auth_status(db, cos_settings_session)


@auth_router.post("/setup", status_code=201)
def setup(body: PasswordIn, db: Session = Depends(get_db)):
    service.setup_password(db, body.password)
    return {"ok": True}


@auth_router.post("/login")
def login(body: PasswordIn, response: Response, db: Session = Depends(get_db)):
    service.login(db, body.password, response)
    return {"ok": True}


@auth_router.post("/logout")
def logout(response: Response, db: Session = Depends(get_db), cos_settings_session: str | None = Cookie(default=None, alias=COOKIE_NAME)):
    service.logout(db, cos_settings_session, response)
    return {"ok": True}


@keys_router.get("")
def keys(db: Session = Depends(get_db)):
    return service.list_keys(db)


@keys_router.put("/{name}")
def save_key(name: str, body: KeyIn, db: Session = Depends(get_db)):
    service.set_key(db, name, body.value)
    return {"ok": True}


@keys_router.delete("/{name}")
def remove_key(name: str, db: Session = Depends(get_db)):
    service.delete_key(db, name)
    return {"ok": True}
