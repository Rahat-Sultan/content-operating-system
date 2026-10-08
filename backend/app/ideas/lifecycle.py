"""
Idea and strategy lifecycle: archive, restore, delete, and no re-proposed duplicates.

Archive is a status change (ideas -> REJECTED, strategies -> archived_at), reversible.
Delete is permanent, so it is refused while any workflow run exists, because runs own
the publications and analytics beneath them.
"""
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.ideas.models import Idea, IdeaStatus
from app.workflows.models import WorkflowRun, WorkflowRunStatus


def title_already_proposed(db: Session, strategy_id: UUID, title: str) -> bool:
    """True if the strategy already has an idea with this title, in any status."""
    return db.query(Idea.id).filter(Idea.strategy_id == strategy_id, Idea.title == title).first() is not None


def add_new_idea_if_unique(db: Session, idea: Idea) -> bool:
    """
    Adds a discovered idea unless its title is already proposed for the strategy. The
    partial unique index on NEW ideas backs this up. A race that gets past the check
    fails the insert, and the savepoint keeps the rest of the discovery run intact.
    """
    if title_already_proposed(db, idea.strategy_id, idea.title):
        return False
    try:
        with db.begin_nested():
            db.add(idea)
            db.flush()
    except IntegrityError:
        return False
    return True


def archive_idea(db: Session, idea_id: UUID, owner_id: UUID) -> Idea:
    # Atomic: only NEW or SELECTED ideas can be archived. In-progress or published ones cannot.
    updated = (
        db.query(Idea)
        .filter(Idea.id == idea_id, Idea.owner_id == owner_id, Idea.status.in_([IdeaStatus.NEW, IdeaStatus.SELECTED]))
        .update({Idea.status: IdeaStatus.REJECTED}, synchronize_session=False)
    )
    if updated != 1:
        db.rollback()
        current = db.query(Idea).filter(Idea.id == idea_id, Idea.owner_id == owner_id).first()
        if current is None:
            raise HTTPException(status_code=404, detail=f"Idea {idea_id} not found.")
        raise HTTPException(status_code=409, detail=f"Idea is {current.status.value}; only NEW or SELECTED ideas can be archived.")
    db.commit()
    return db.query(Idea).filter(Idea.id == idea_id).one()


def restore_idea(db: Session, idea_id: UUID, owner_id: UUID) -> Idea:
    try:
        updated = (
            db.query(Idea)
            .filter(Idea.id == idea_id, Idea.owner_id == owner_id, Idea.status == IdeaStatus.REJECTED)
            .update({Idea.status: IdeaStatus.NEW}, synchronize_session=False)
        )
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="A new idea with this title already exists for the strategy. Archive or delete it first.")
    if updated != 1:
        raise HTTPException(status_code=409, detail="Only archived ideas can be restored.")
    return db.query(Idea).filter(Idea.id == idea_id).one()


def delete_idea(db: Session, idea_id: UUID, owner_id: UUID) -> None:
    idea = db.query(Idea).filter(Idea.id == idea_id, Idea.owner_id == owner_id).first()
    if idea is None:
        raise HTTPException(status_code=404, detail=f"Idea {idea_id} not found.")
    runs = db.query(WorkflowRun).filter(WorkflowRun.idea_id == idea_id).count()
    if runs:
        raise HTTPException(
            status_code=409,
            detail=f"This idea has {runs} workflow run(s) and their drafts, approvals and publications. Archive it instead; deleting it would remove those records.",
        )
    db.delete(idea)
    db.commit()


def archive_strategy(db: Session, strategy_id: UUID, owner_id: UUID) -> None:
    result = db.execute(
        text("UPDATE content_strategies SET archived_at = now() WHERE id = :id AND owner_id = :owner AND archived_at IS NULL"),
        {"id": strategy_id, "owner": owner_id},
    )
    db.commit()
    if result.rowcount != 1:
        raise HTTPException(status_code=409, detail="Strategy is missing or already archived.")


def restore_strategy(db: Session, strategy_id: UUID, owner_id: UUID) -> None:
    result = db.execute(
        text("UPDATE content_strategies SET archived_at = NULL WHERE id = :id AND owner_id = :owner AND archived_at IS NOT NULL"),
        {"id": strategy_id, "owner": owner_id},
    )
    db.commit()
    if result.rowcount != 1:
        raise HTTPException(status_code=409, detail="Strategy is missing or not archived.")


def delete_strategy(db: Session, strategy_id: UUID, owner_id: UUID) -> dict:
    """Deletes a strategy and its unrun ideas. Refused if any of its ideas has a workflow run."""
    from app.strategies.models import ContentStrategy
    strategy = db.query(ContentStrategy).filter(ContentStrategy.id == strategy_id, ContentStrategy.owner_id == owner_id).first()
    if strategy is None:
        raise HTTPException(status_code=404, detail=f"Strategy {strategy_id} not found.")
    runs = (
        db.query(WorkflowRun)
        .filter(WorkflowRun.strategy_id == strategy_id)
        .count()
    )
    if runs:
        raise HTTPException(
            status_code=409,
            detail=f"This strategy has {runs} workflow run(s). Archive it instead; deleting it would remove their drafts and publications.",
        )
    ideas = db.query(Idea).filter(Idea.strategy_id == strategy_id).count()
    db.delete(strategy)
    db.commit()
    return {"deleted_strategy_id": str(strategy_id), "deleted_ideas": ideas}


ACTIVE_RUN_STATUSES = [
    WorkflowRunStatus.PENDING, WorkflowRunStatus.RUNNING,
    WorkflowRunStatus.PAUSED, WorkflowRunStatus.NEEDS_REVIEW,
]


def stop_and_delete_idea(db: Session, idea_id: UUID, owner_id: UUID) -> dict:
    """
    Stops every workflow run of the idea, then deletes the idea and everything under it.

    - A post that is being published right now is never interrupted: the delete is refused until it finishes.
    - Queued steps are removed. A step already running cannot be killed inside the worker, so the
      result is "stopping"; the caller retries and the delete completes once nothing is running.
    - Published LinkedIn posts stay on LinkedIn. Only their records here are deleted.
    """
    from app.scheduler.models import JobStatus, JobType, ScheduledJob
    from app.publishing.models import Publication, PublicationStatus
    from datetime import datetime, timezone

    idea = db.query(Idea).filter(Idea.id == idea_id, Idea.owner_id == owner_id).first()
    if idea is None:
        raise HTTPException(status_code=404, detail=f"Idea {idea_id} not found.")

    run_ids = [r.id for r in db.query(WorkflowRun.id).filter(WorkflowRun.idea_id == idea_id).all()]
    if run_ids:
        publishing = (
            db.query(WorkflowRun)
            .filter(WorkflowRun.idea_id == idea_id, WorkflowRun.status == WorkflowRunStatus.PUBLISHING)
            .count()
        )
        if publishing:
            raise HTTPException(
                status_code=409,
                detail="A post for this idea is being published right now. Wait for it to finish, then delete.",
            )
        now = datetime.now(timezone.utc)
        # 1. No new work: runs become CANCELLED and their queued steps are removed.
        db.query(WorkflowRun).filter(
            WorkflowRun.idea_id == idea_id, WorkflowRun.status.in_(ACTIVE_RUN_STATUSES),
        ).update({WorkflowRun.status: WorkflowRunStatus.CANCELLED, WorkflowRun.resolved_at: now},
                 synchronize_session=False)
        run_id_strings = [str(r) for r in run_ids]
        db.query(ScheduledJob).filter(
            ScheduledJob.job_type == JobType.WORKFLOW_RUN,
            ScheduledJob.status == JobStatus.PENDING,
            ScheduledJob.payload["workflow_run_id"].astext.in_(run_id_strings),
        ).update({ScheduledJob.status: JobStatus.FAILED, ScheduledJob.error: "stopped: idea deleted",
                  ScheduledJob.completed_at: now}, synchronize_session=False)
        db.commit()

        # 2. A step that is running right now finishes first; it cannot be interrupted safely.
        still_running = (
            db.query(ScheduledJob)
            .filter(
                ScheduledJob.job_type == JobType.WORKFLOW_RUN,
                ScheduledJob.status == JobStatus.RUNNING,
                ScheduledJob.payload["workflow_run_id"].astext.in_(run_id_strings),
            )
            .count()
        )
        if still_running:
            return {"status": "stopping", "message": "A step is still running. It stops at its next checkpoint, then the idea is deleted."}

    published = 0
    if run_ids:
        from app.content.models import Content, ContentVersion
        published = (
            db.query(Publication)
            .join(ContentVersion, ContentVersion.id == Publication.content_version_id)
            .join(Content, Content.id == ContentVersion.content_id)
            .filter(Content.workflow_run_id.in_(run_ids), Publication.status == PublicationStatus.PUBLISHED)
            .count()
        )
    # 3. Delete: runs, drafts, approvals, publications and analytics go with it (cascade).
    db.delete(idea)
    db.commit()
    return {"status": "deleted", "published_posts_kept_on_platform": published}


def advance_idea(db: Session, idea_id, owner_id, to: IdeaStatus, from_statuses: list[IdeaStatus]) -> bool:
    """
    Moves an idea forward one stage. Atomic: the UPDATE only applies when the idea is
    still in one of from_statuses, so a repeat call is a no-op. Does not commit; the
    caller's transaction commits it with the change that caused the move.
    """
    updated = (
        db.query(Idea)
        .filter(Idea.id == idea_id, Idea.owner_id == owner_id, Idea.status.in_(from_statuses))
        .update({Idea.status: to}, synchronize_session=False)
    )
    return updated == 1


def select_idea(db: Session, idea_id: UUID, owner_id: UUID) -> Idea:
    """Moves a NEW idea to SELECTED. Atomic: the UPDATE only applies from NEW."""
    updated = (
        db.query(Idea)
        .filter(Idea.id == idea_id, Idea.owner_id == owner_id, Idea.status == IdeaStatus.NEW)
        .update({Idea.status: IdeaStatus.SELECTED}, synchronize_session=False)
    )
    if updated != 1:
        db.rollback()
        current = db.query(Idea).filter(Idea.id == idea_id, Idea.owner_id == owner_id).first()
        if current is None:
            raise HTTPException(status_code=404, detail=f"Idea {idea_id} not found.")
        raise HTTPException(status_code=409, detail=f"Idea is {current.status.value}; only NEW ideas can be selected.")
    db.commit()
    return db.query(Idea).filter(Idea.id == idea_id).one()
