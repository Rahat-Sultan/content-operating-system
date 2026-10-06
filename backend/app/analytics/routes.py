from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.accounts.models import User
from app.accounts.service import current_user
from app.db import get_db
from app.analytics.dashboard import build_summary

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/summary")
def analytics_summary(include_test: bool = False, platform: str | None = None, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Cross-post summary. Test and placeholder publications are hidden unless include_test=true."""
    return build_summary(db, include_test=include_test, platform=platform, owner_id=user.id)
