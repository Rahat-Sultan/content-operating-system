"""
Marks a publication as deleted upstream (the post is gone from the platform).

Buffer answers NOT_FOUND for a post that no longer exists. Polling stops for such a
post, and the UI says "Deleted on LinkedIn". One atomic jsonb_set, so it never races
another writer.
"""
import json
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

DELETED_KEY = "deleted_upstream_at"


def mark_deleted_upstream(db: Session, publication_id: UUID, detail: str) -> None:
    value = {"at": datetime.now(timezone.utc).isoformat(), "detail": detail[:300]}
    db.execute(
        text(
            "UPDATE publications "
            "SET publication_metadata = jsonb_set(COALESCE(publication_metadata, '{}'::jsonb), "
            "    CAST(:path AS text[]), CAST(:value AS jsonb)) "
            "WHERE id = :id"
        ),
        {"path": "{" + DELETED_KEY + "}", "value": json.dumps(value), "id": publication_id},
    )
    db.commit()


def deleted_upstream_at(publication) -> str | None:
    meta = publication.publication_metadata or {}
    value = meta.get(DELETED_KEY)
    if isinstance(value, dict):
        return value.get("at")
    return value
