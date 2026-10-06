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
from app.publishing.platforms import PLATFORMS, normalize_platform

# external_id prefixes written by local test providers or placeholders. Not real posts.
TEST_ID_PREFIXES = ("linkedin_", "test-ext-", "stub_", "buffer_idea_", "TEMP-")


def _deleted_at(pub) -> str | None:
    from app.analytics.upstream import deleted_upstream_at
    return deleted_upstream_at(pub)


def _is_test_post(external_id: str | None) -> bool:
    return bool(external_id) and external_id.startswith(TEST_ID_PREFIXES)


def build_summary(db: Session, include_test: bool = False, platform: str | None = None, owner_id=None) -> dict[str, Any]:
    pubs = (
        db.query(Publication)
        .filter(Publication.status == PublicationStatus.PUBLISHED, Publication.owner_id == owner_id)
        .order_by(Publication.published_at.desc().nulls_last(), Publication.created_at.desc())
        .all()
    )
    if not include_test:
        pubs = [p for p in pubs if not _is_test_post(p.external_id)]
    all_pubs = pubs  # for the per-platform breakdown
    if platform:
        pubs = [p for p in pubs if normalize_platform(p.platform) == normalize_platform(platform)]
    pub_ids = [p.id for p in all_pubs]

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
    idea_title_for: dict = {}
    if pub_ids:
        pairs = (
            db.query(Publication.id, Content.workflow_run_id)
            .join(ContentVersion, ContentVersion.id == Publication.content_version_id)
            .join(Content, Content.id == ContentVersion.content_id)
            .filter(Publication.id.in_(pub_ids))
            .all()
        )
        run_for = {pid: str(run_id) for pid, run_id in pairs}

        # Idea title for each publication, so the table names the post by its idea.
        from app.workflows.models import WorkflowRun
        from app.ideas.models import Idea
        title_rows = (
            db.query(Publication.id, Idea.title)
            .join(ContentVersion, ContentVersion.id == Publication.content_version_id)
            .join(Content, Content.id == ContentVersion.content_id)
            .join(WorkflowRun, WorkflowRun.id == Content.workflow_run_id)
            .join(Idea, Idea.id == WorkflowRun.idea_id)
            .filter(Publication.id.in_(pub_ids))
            .all()
        )
        idea_title_for = {pid: title for pid, title in title_rows}

    posts = []
    for pub in pubs:
        snap = latest.get(pub.id)
        m = snap.metrics if snap else {}
        posts.append({
            "publication_id": str(pub.id),
            "workflow_run_id": run_for.get(pub.id),
            "idea_title": idea_title_for.get(pub.id),
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
            "deleted_upstream_at": _deleted_at(pub),
        })

    known = [p["key"] for p in PLATFORMS]
    from app.platform_settings.service import platform_views
    ready = {v["key"]: v["ready"] for v in platform_views(db, owner_id)}
    breakdown = []
    for info in PLATFORMS:
        key = info["key"]
        rows = [p for p in all_pubs if normalize_platform(p.platform) == key]
        breakdown.append({"key": key, "label": info["label"], "connected": ready.get(key, False),
                          "post_count": len(rows)})
    for key in sorted({normalize_platform(p.platform) for p in all_pubs} - set(known)):
        breakdown.append({"key": key, "label": key, "connected": False,
                          "post_count": len([p for p in all_pubs if normalize_platform(p.platform) == key])})

    with_data = [p for p in posts if p["has_snapshot"]]
    return {
        "platform": normalize_platform(platform) if platform else None,
        "platforms": breakdown,
        "post_count": len(posts),
        "posts_with_metrics": len(with_data),
        "total_impressions": sum(p["impressions"] or 0 for p in with_data),
        "total_reactions": sum(p["reactions"] or 0 for p in with_data),
        "total_comments": sum(p["comments"] or 0 for p in with_data),
        "include_test": include_test,
        "posts": posts,
    }
