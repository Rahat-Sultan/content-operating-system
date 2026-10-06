"""
Post images in Supabase Storage. Each account's files sit in its own folder, under a random
name, so a link cannot be guessed. Buffer fetches the image from the public URL.
"""
import uuid

import httpx
from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import settings


def configured() -> bool:
    return bool(settings.supabase_url and settings.supabase_secret_key and settings.supabase_bucket)


def storage_used_bytes(db: Session, owner_id) -> int:
    """Bytes this account has stored, from its image records."""
    row = db.execute(text("""
        SELECT COALESCE(SUM((m.asset_metadata->>'size_bytes')::bigint), 0)
        FROM media_assets m
        JOIN content_versions v ON v.id = m.content_version_id
        JOIN content c ON c.id = v.content_id
        JOIN workflow_runs w ON w.id = c.workflow_run_id
        WHERE w.owner_id = :owner
    """), {"owner": owner_id}).scalar()
    return int(row or 0)


def check_quota(db: Session, owner_id, new_bytes: int) -> None:
    limit = settings.user_storage_limit_mb * 1024 * 1024
    used = storage_used_bytes(db, owner_id)
    if used + new_bytes > limit:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Storage limit reached: {used / 1048576:.1f} MB of {settings.user_storage_limit_mb} MB used. Delete old images to add more.",
        )


def upload(owner_id, data: bytes, mime_type: str) -> tuple[str, int]:
    """Uploads one image into the account's folder. Returns (public URL, size in bytes)."""
    if not configured():
        raise HTTPException(status_code=503, detail="Supabase storage is not configured in backend/.env.")
    ext = "png" if mime_type == "image/png" else "jpg" if mime_type in ("image/jpeg", "image/jpg") else "bin"
    path = f"{owner_id}/{uuid.uuid4().hex}.{ext}"
    base = settings.supabase_url.rstrip("/")
    headers = {"apikey": settings.supabase_secret_key,
               "Authorization": f"Bearer {settings.supabase_secret_key}",
               "Content-Type": mime_type}
    with httpx.Client(timeout=60) as client:
        res = client.post(f"{base}/storage/v1/object/{settings.supabase_bucket}/{path}", headers=headers, content=data)
    if res.status_code not in (200, 201):
        raise HTTPException(status_code=502, detail=f"Image upload failed (Supabase HTTP {res.status_code}).")
    return f"{base}/storage/v1/object/public/{settings.supabase_bucket}/{path}", len(data)
