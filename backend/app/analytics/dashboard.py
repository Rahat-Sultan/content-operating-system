"""
Cross-post analytics summary: one row per published post, from its newest valid
snapshot (not a stub, not quarantined). Read-only.
"""
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.analytics.models import Analytics
from app.publishing.models import Publication, PublicationStatus
from app.content.models import Content, ContentVersion

# external_id prefixes written by local test providers or placeholders. Not real posts.
TEST_ID_PREFIXES = ("linkedin_", "test-ext-", "stub_", "buffer_idea_", "TEMP-")


def _is_test_post(external_id: str | None) -> bool:
    return bool(external_id) and external_id.startswith(TEST_ID_PREFIXES)


def build_summary(db: Session, include_test: bool = False) -> dict[str, Any]:
    pubs = (
        db.query(Publication)
        .filter(Publication.status == PublicationStatus.PUBLISHED)
        .order_by(Publication.published_at.desc().nulls_last(), Publication.created_at.desc())
        .all()
    )
    if not include_test:
        pubs = [p for p in pubs if not _is_test_post(p.external_id)]
    pub_ids = [p.id for p in pubs]

    # Newest valid snapshot and snapshot count per publication, in one pass.
    latest: dict = {}
    counts: dict = {}
    if pub_ids:
        rows = (
            db.query(Analytics)
            .filter(
                Analytics.publication_id.in_(pub_ids),
                text("COALESCE((metrics->>'is_stub')::boolean, false) IS FALSE"),
                text("metrics->>'invalid_reason' IS NULL"),
            )
            .order_by(Analytics.collected_at.desc())
            .all()
        )
        for snap in rows:
            counts[snap.publication_id] = counts.get(snap.publication_id, 0) + 1
            latest.setdefault(snap.publication_id, snap)

    # Workflow run for each publication (for linking to its page).
    run_for: dict = {}
    if pub_ids:
        pairs = (
            db.query(Publication.id, Content.workflow_run_id)
            .join(ContentVersion, ContentVersion.id == Publication.content_version_id)
            .join(Content, Content.id == ContentVersion.content_id)
            .filter(Publication.id.in_(pub_ids))
            .all()
        )
        run_for = {pid: str(run_id) for pid, run_id in pairs}

    posts = []
    for pub in pubs:
        snap = latest.get(pub.id)
        m = snap.metrics if snap else {}
        posts.append({
            "publication_id": str(pub.id),
            "workflow_run_id": run_for.get(pub.id),
            "platform": pub.platform,
            "external_id": pub.external_id,
            "published_at": pub.published_at.isoformat() if pub.published_at else None,
            "has_snapshot": snap is not None,
            "collected_at": snap.collected_at.isoformat() if snap else None,
            "provider": m.get("provider"),
            "impressions": m.get("impressions"),
            "reactions": m.get("reactions", m.get("likes")),
            "comments": m.get("comments"),
            "clicks": m.get("clicks"),
            "shares": m.get("shares"),
            "snapshot_count": counts.get(pub.id, 0),
            "is_test_post": _is_test_post(pub.external_id),
        })

    with_data = [p for p in posts if p["has_snapshot"]]
    return {
        "post_count": len(posts),
        "posts_with_metrics": len(with_data),
        "total_impressions": sum(p["impressions"] or 0 for p in with_data),
        "total_reactions": sum(p["reactions"] or 0 for p in with_data),
        "total_comments": sum(p["comments"] or 0 for p in with_data),
        "include_test": include_test,
        "posts": posts,
    }
