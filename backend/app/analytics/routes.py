from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.analytics.dashboard import build_summary

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/summary")
def analytics_summary(include_test: bool = False, platform: str | None = None, db: Session = Depends(get_db)):
    """Cross-post summary. Test and placeholder publications are hidden unless include_test=true."""
    return build_summary(db, include_test=include_test, platform=platform)
