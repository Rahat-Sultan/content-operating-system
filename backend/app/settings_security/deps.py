from fastapi import Cookie, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.settings_security.service import COOKIE_NAME, require_session


def settings_session(
    db: Session = Depends(get_db),
    cos_settings_session: str | None = Cookie(default=None, alias=COOKIE_NAME),
) -> None:
    """Dependency for every Settings route that changes or reveals configuration."""
    require_session(db, cos_settings_session)
