from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db import get_db
from app.platform_settings.service import platform_views, test_platform, update_platform

from app.accounts.models import User
from app.accounts.service import current_user
from app.settings_security.vault import require_vault_unlocked

router = APIRouter(prefix="/settings/platforms", tags=["settings"])


class PlatformSettingsIn(BaseModel):
    enabled: bool = False
    display_name: str | None = Field(default=None, max_length=80)
    channel_id: str | None = Field(default=None, max_length=64)
    notes: str | None = Field(default=None, max_length=500)


@router.get("", dependencies=[Depends(require_vault_unlocked)])
def list_platform_settings(db: Session = Depends(get_db), user: User = Depends(current_user)) -> list[dict[str, Any]]:
    return platform_views(db, user.id)


@router.put("/{key}", dependencies=[Depends(require_vault_unlocked)])
def save_platform_settings(key: str, body: PlatformSettingsIn, db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict[str, Any]:
    return update_platform(db, user.id, key, body.model_dump())


@router.post("/{key}/test", dependencies=[Depends(require_vault_unlocked)])
def test_platform_connection(key: str, db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict[str, Any]:
    """Read-only check. Never publishes."""
    return test_platform(db, user.id, key)
