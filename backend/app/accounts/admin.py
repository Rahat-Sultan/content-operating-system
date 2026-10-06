"""Admin view: every account, how many posts it has, and the storage each uses."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.accounts.models import User
from app.accounts.service import current_user
from app.config import settings
from app.db import get_db

router = APIRouter(prefix="/admin", tags=["admin"])


def admin_only(user: User = Depends(current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admins only.")
    return user


@router.get("/users")
def list_users(db: Session = Depends(get_db), admin: User = Depends(admin_only)):
    rows = db.execute(text("""
        SELECT u.id, u.email, u.display_name, u.auth_provider, u.is_admin, u.created_at,
               (SELECT count(*) FROM publications p WHERE p.owner_id = u.id AND p.status = 'PUBLISHED') AS posts,
               (SELECT count(*) FROM ideas i WHERE i.owner_id = u.id) AS ideas,
               (SELECT COALESCE(SUM((m.asset_metadata->>'size_bytes')::bigint), 0)
                  FROM media_assets m
                  JOIN content_versions v ON v.id = m.content_version_id
                  JOIN content c ON c.id = v.content_id
                  JOIN workflow_runs w ON w.id = c.workflow_run_id
                 WHERE w.owner_id = u.id) AS storage_bytes
        FROM users u ORDER BY u.created_at
    """)).mappings().all()
    limit = settings.user_storage_limit_mb * 1024 * 1024
    return {
        "accounts": len(rows),
        "storage_limit_mb_per_account": settings.user_storage_limit_mb,
        "users": [
            {"id": str(r["id"]), "email": r["email"], "name": r["display_name"],
             "sign_in": r["auth_provider"], "is_admin": r["is_admin"],
             "created_at": r["created_at"].isoformat(), "posts": r["posts"], "ideas": r["ideas"],
             "storage_mb": round(int(r["storage_bytes"]) / 1048576, 2),
             "storage_limit_mb": settings.user_storage_limit_mb,
             "storage_percent": round(100 * int(r["storage_bytes"]) / limit, 1) if limit else 0}
            for r in rows
        ],
    }
