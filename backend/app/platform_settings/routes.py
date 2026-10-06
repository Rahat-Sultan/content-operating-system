from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db import get_db
from app.platform_settings.service import platform_views, test_platform, update_platform

from app.settings_security.deps import settings_session

router = APIRouter(prefix="/settings/platforms", tags=["settings"], dependencies=[Depends(settings_session)])


class PlatformSettingsIn(BaseModel):
    enabled: bool = False
    display_name: str | None = Field(default=None, max_length=80)
    channel_id: str | None = Field(default=None, max_length=64)
    notes: str | None = Field(default=None, max_length=500)


@router.get("")
def list_platform_settings(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    return platform_views(db)


@router.put("/{key}")
def save_platform_settings(key: str, body: PlatformSettingsIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    return update_platform(db, key, body.model_dump())


@router.post("/{key}/test")
def test_platform_connection(key: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    """Read-only check. Never publishes."""
    return test_platform(db, key)
