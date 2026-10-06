from uuid import UUID, uuid4
from datetime import datetime, timezone
import psycopg
from psycopg.errors import UniqueViolation
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from fastapi import HTTPException, status

from app.ideas.models import Idea
from app.strategies.models import ContentStrategy
from app.scheduler.workflow_jobs import enqueue_workflow_job
from app.workflows.models import WorkflowRun, WorkflowRunStatus
from app.workflows.models import WorkflowRun, WorkflowRunStatus, Research, ContentBrief
from app.content.models import Content, ContentVersion, Approval, ApprovalStatus


ACTIVE_STATUSES = [
    WorkflowRunStatus.PENDING,
    WorkflowRunStatus.RUNNING,
    WorkflowRunStatus.PAUSED,
    WorkflowRunStatus.NEEDS_REVIEW,
    WorkflowRunStatus.PUBLISHING,
]


def get_workflow_run(db: Session, run_id: UUID, owner_id=None) -> WorkflowRun:
    query = db.query(WorkflowRun).filter(WorkflowRun.id == run_id)
    if owner_id is not None:
        query = query.filter(WorkflowRun.owner_id == owner_id)
    run = query.first()
    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workflow run {run_id} not found."
        )
    return run


def create_workflow_run(
    db: Session,
    strategy_id: UUID,
    idea_id: UUID,
    owner_id=None,
) -> WorkflowRun:
    # 1. Validate strategy and idea exist
    strategy = db.query(ContentStrategy).filter(ContentStrategy.id == strategy_id, ContentStrategy.owner_id == owner_id).first()
    if not strategy:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Strategy {strategy_id} not found."
        )

    idea = db.query(Idea).filter(Idea.id == idea_id, Idea.owner_id == owner_id).first()
    if not idea:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Idea {idea_id} not found."
        )

    # 2. Fast-path application-level pre-check (for non-racing case)
    existing_active = (
        db.query(WorkflowRun)
        .filter(
            WorkflowRun.idea_id == idea_id,
            WorkflowRun.status.in_(ACTIVE_STATUSES),
        )
        .first()
    )
    if existing_active:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "ACTIVE_WORKFLOW_EXISTS",
                "message": "An active workflow already exists for this idea.",
                "workflow_run_id": str(existing_active.id),
                "status": existing_active.status.value,
            },
        )

    # 3. Insert workflow_runs row protected against race conditions
    run_id = uuid4()
    run = WorkflowRun(
        id=run_id,
        owner_id=owner_id,
        strategy_id=strategy_id,
        idea_id=idea_id,
        status=WorkflowRunStatus.PENDING,
        run_metadata={},
    )
    db.add(run)
    # The idea moves to In progress with the run, in the same commit.
    from app.ideas.lifecycle import advance_idea
    from app.ideas.models import IdeaStatus
    advance_idea(db, idea_id, owner_id, IdeaStatus.IN_PROGRESS, [IdeaStatus.NEW, IdeaStatus.SELECTED])
    # Queued in the same commit as the run: a crash cannot leave a run without its start job.
    enqueue_workflow_job(db, "start", run_id, owner_id=owner_id)

    try:
        db.commit()
        db.refresh(run)
    except IntegrityError as exc:
        db.rollback()

        # Specifically check if the failure is the uq_active_workflow_per_idea unique constraint violation
        is_active_workflow_violation = False
        if isinstance(exc.orig, UniqueViolation):
            # Check constraint name on psycopg UniqueViolation or in error message
            diag = getattr(exc.orig, "diag", None)
            constraint_name = getattr(diag, "constraint_name", None)
            if constraint_name == "uq_active_workflow_per_idea":
                is_active_workflow_violation = True
            elif "uq_active_workflow_per_idea" in str(exc.orig):
                is_active_workflow_violation = True
        elif "uq_active_workflow_per_idea" in str(exc):
            is_active_workflow_violation = True

        if is_active_workflow_violation:
            # Query the newly committed winning run to populate the exact error message
            active_run = (
                db.query(WorkflowRun)
                .filter(
                    WorkflowRun.idea_id == idea_id,
                    WorkflowRun.status.in_(ACTIVE_STATUSES),
                )
                .first()
            )
            detail_payload = {
                "code": "ACTIVE_WORKFLOW_EXISTS",
                "message": "An active workflow already exists for this idea.",
                "workflow_run_id": str(active_run.id) if active_run else "",
                "status": active_run.status.value if active_run else "RUNNING",
            }

            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=detail_payload,
            ) from exc

        # Any other database integrity error should propagate as normal
        raise

    return run


def process_approval_decision(
    db: Session,
    workflow_run_id: UUID,
    content_version_id: UUID,
    decision: ApprovalStatus,
    feedback: str | None = None,
    owner_id=None,
) -> tuple[WorkflowRun, Approval]:
    """
    Processes an approval decision in a single atomic transaction:
    1. Validates that the workflow run exists.
    2. Validates that content_version_id matches the latest draft awaiting review.
    3. Performs conditional UPDATE on workflow_runs WHERE id = :id AND status = 'NEEDS_REVIEW'.
       If rowcount != 1 -> roll back and return 409 Conflict.
    4. Inserts an approvals row tied to content_version_id.
    5. Commits transaction and returns (workflow_run, approval).
    """
    # 1. Fetch workflow run
    run = db.query(WorkflowRun).filter(WorkflowRun.id == workflow_run_id, WorkflowRun.owner_id == owner_id).first()
    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workflow run {workflow_run_id} not found."
        )

    # 2. Check version lock (prevent approving a stale or incorrect version)
    content = db.query(Content).filter(Content.workflow_run_id == workflow_run_id).first()
    if not content:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No content found for workflow run {workflow_run_id}."
        )

    latest_version = (
        db.query(ContentVersion)
        .filter(ContentVersion.content_id == content.id)
        .order_by(ContentVersion.version_number.desc())
        .first()
    )
    if not latest_version:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No content versions found for workflow run {workflow_run_id}."
        )

    if latest_version.id != content_version_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Version mismatch: Submitted content_version_id {content_version_id} "
                f"does not match the latest version {latest_version.id} (v{latest_version.version_number})."
            )
        )

    # 3. Determine next status based on decision
    next_status = (
        WorkflowRunStatus.REJECTED
        if decision == ApprovalStatus.REJECTED
        else WorkflowRunStatus.RUNNING
    )

    # 4. Atomic conditional UPDATE:
    # UPDATE workflow_runs SET status = :next_status WHERE id = :id AND status = 'NEEDS_REVIEW'
    updated_rows = (
        db.query(WorkflowRun)
        .filter(
            WorkflowRun.id == workflow_run_id,
            WorkflowRun.status == WorkflowRunStatus.NEEDS_REVIEW,
        )
        .update(
            {WorkflowRun.status: next_status},
            synchronize_session=False,
        )
    )

    if updated_rows != 1:
        db.rollback()
        # Fetch current status for detailed 409 error
        current_run = db.query(WorkflowRun).filter(WorkflowRun.id == workflow_run_id).first()
        current_status = current_run.status.value if current_run else "UNKNOWN"
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Conflict: Workflow run {workflow_run_id} is not in NEEDS_REVIEW status "
                f"(current status is '{current_status}')."
            )
        )

    # 5. Insert Approval row
    approval_record = Approval(
        id=uuid4(),
        content_version_id=content_version_id,
        status=decision,
        feedback=feedback,
    )
    db.add(approval_record)

    # Resume job in the same commit as the status change and the approval row.
    enqueue_workflow_job(
        db, "resume", run.id,
        decision={"decision": decision.value, "feedback": feedback}, owner_id=run.owner_id,
    )

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Conflict saving approval decision: {str(exc)}",
        ) from exc

    db.refresh(run)
    db.refresh(approval_record)
    return run, approval_record


def get_research_for_workflow_run(db: Session, workflow_run_id: UUID) -> Research:
    research = db.query(Research).filter(Research.workflow_run_id == workflow_run_id).first()
    if not research:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Research artifact not found for workflow run {workflow_run_id}."
        )
    return research


def get_brief_for_workflow_run(db: Session, workflow_run_id: UUID) -> ContentBrief:
    brief = db.query(ContentBrief).filter(ContentBrief.workflow_run_id == workflow_run_id).first()
    if not brief:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Content brief artifact not found for workflow run {workflow_run_id}."
        )
    return brief

def get_draft_for_workflow_run(db: Session, workflow_run_id: UUID) -> tuple[Content, list[ContentVersion]]:
    """
    Returns the Content container and all its versions for a workflow run,
    ordered with the most recent version first (index 0 = current draft).
    """
    content = (
        db.query(Content)
        .filter(Content.workflow_run_id == workflow_run_id)
        .first()
    )
    if content is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No content found for workflow run {workflow_run_id}.",
        )

    versions = (
        db.query(ContentVersion)
        .filter(ContentVersion.content_id == content.id)
        .order_by(ContentVersion.version_number.desc())
        .all()
    )
    return content, versions

def create_human_edit_version(
    db: Session,
    workflow_run_id: UUID,
    title: str | None,
    body: str,
    owner_id=None,
) -> ContentVersion:
    """
    Saves a human edit as a NEW immutable version (origin HUMAN_EDIT). Existing versions
    are never changed (ADR-008). Allowed only while the run waits for review.

    The run row is locked FOR UPDATE, so an edit and an approval cannot interleave. The
    UNIQUE (content_id, version_number) constraint also rejects a concurrent second edit.
    """
    from app.content.models import ContentVersionOrigin

    run = (
        db.query(WorkflowRun)
        .filter(WorkflowRun.id == workflow_run_id, WorkflowRun.owner_id == owner_id)
        .with_for_update()
        .first()
    )
    if run is None:
        db.rollback()
        raise HTTPException(status_code=404, detail=f"Workflow run {workflow_run_id} not found.")
    if run.status != WorkflowRunStatus.NEEDS_REVIEW:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Drafts can only be edited while the run awaits review (current status: {run.status.value}).",
        )

    content = db.query(Content).filter(Content.workflow_run_id == workflow_run_id).first()
    if content is None:
        db.rollback()
        raise HTTPException(status_code=404, detail=f"No content found for workflow run {workflow_run_id}.")

    latest = (
        db.query(ContentVersion)
        .filter(ContentVersion.content_id == content.id)
        .order_by(ContentVersion.version_number.desc())
        .first()
    )
    new_version = ContentVersion(
        id=uuid4(),
        content_id=content.id,
        version_number=(latest.version_number + 1) if latest else 1,
        origin=ContentVersionOrigin.HUMAN_EDIT,
        title=(title or None),
        body=body,
    )
    db.add(new_version)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Another edit was saved at the same time. Reload and try again.") from exc
    db.refresh(new_version)
    return new_version


def retry_publish(db: Session, run_id: UUID, owner_id) -> WorkflowRun:
    """
    Retries publishing for a FAILED run whose latest draft is already approved.

    The claim is a conditional UPDATE (FAILED -> PUBLISHING), so two clicks cannot both
    publish. The publish itself goes through the same publisher node the graph uses,
    which keeps idempotency and the image checks in one place.
    """
    from app.accounts.context import set_current_owner
    from app.graph.nodes.publisher import publisher_node

    run = db.query(WorkflowRun).filter(WorkflowRun.id == run_id, WorkflowRun.owner_id == owner_id).first()
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Workflow run {run_id} not found.")

    content = db.query(Content).filter(Content.workflow_run_id == run_id).first()
    latest = None
    if content:
        latest = (
            db.query(ContentVersion)
            .filter(ContentVersion.content_id == content.id)
            .order_by(ContentVersion.version_number.desc())
            .first()
        )
    approval = (
        db.query(Approval).filter(Approval.content_version_id == latest.id).first() if latest else None
    )
    if latest is None or approval is None or approval.status != ApprovalStatus.APPROVED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only a run whose latest draft was approved can retry publishing.",
        )

    claimed = (
        db.query(WorkflowRun)
        .filter(WorkflowRun.id == run_id, WorkflowRun.owner_id == owner_id, WorkflowRun.status == WorkflowRunStatus.FAILED)
        .update({"status": WorkflowRunStatus.PUBLISHING, "error": None}, synchronize_session=False)
    )
    db.commit()
    if claimed != 1:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Run is not in FAILED state.")

    set_current_owner(owner_id)
    try:
        publisher_node({"current_content_version_id": latest.id, "workflow_run_id": run_id})
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Publishing failed again: {exc}",
        )

    db.query(WorkflowRun).filter(
        WorkflowRun.id == run_id, WorkflowRun.status == WorkflowRunStatus.PUBLISHING
    ).update({"status": WorkflowRunStatus.COMPLETED}, synchronize_session=False)
    db.commit()
    db.expire_all()
    return db.query(WorkflowRun).filter(WorkflowRun.id == run_id).first()
