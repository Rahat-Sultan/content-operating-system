from pydantic import BaseModel, Field
from uuid import UUID
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.workflows.schemas import (
    CreateWorkflowRunRequest,
    WorkflowRunResponse,
    ApprovalDecisionRequest,
    ApprovalDecisionResponse,
    ResearchResponse,
    ContentBriefResponse,
    ContentDraftResponse,
    ContentVersionSummary,
)
from app.publishing.schemas import PublicationResponse
from app.workflows.service import (
    create_workflow_run,
    get_workflow_run,
    process_approval_decision,
    get_research_for_workflow_run,
    get_brief_for_workflow_run,
    get_draft_for_workflow_run,
)

from app.scheduler.heartbeat import scheduler_running

router = APIRouter(prefix="/workflow-runs", tags=["workflow-runs"])


@router.post("", response_model=WorkflowRunResponse, status_code=200)
def start_workflow_run(
    request: CreateWorkflowRunRequest,
    db: Session = Depends(get_db),
):
    # Queues a durable start job; the scheduler worker runs the graph.
    run = create_workflow_run(
        db=db,
        strategy_id=request.strategy_id,
        idea_id=request.idea_id,
    )

    return WorkflowRunResponse(
        workflow_run_id=run.id,
        strategy_id=run.strategy_id,
        idea_id=run.idea_id,
        status=run.status,
        error=run.error,
        created_at=run.created_at,
        resolved_at=run.resolved_at,
        worker_running=scheduler_running(db),
    )


@router.get("", response_model=list[WorkflowRunResponse])
def list_workflow_runs(
    db: Session = Depends(get_db),
):
    from app.workflows.models import WorkflowRun
    runs = db.query(WorkflowRun).order_by(WorkflowRun.created_at.desc()).limit(20).all()
    return [
        WorkflowRunResponse(
            workflow_run_id=r.id,
            strategy_id=r.strategy_id,
            idea_id=r.idea_id,
            status=r.status,
            error=r.error,
            created_at=r.created_at,
            resolved_at=r.resolved_at,
        )
        for r in runs
    ]


@router.get("/{id}", response_model=WorkflowRunResponse)
def read_workflow_run(
    id: UUID,
    db: Session = Depends(get_db),
):
    run = get_workflow_run(db, id)
    return WorkflowRunResponse(
        workflow_run_id=run.id,
        strategy_id=run.strategy_id,
        idea_id=run.idea_id,
        status=run.status,
        error=run.error,
        created_at=run.created_at,
        resolved_at=run.resolved_at,
        worker_running=scheduler_running(db),
    )


@router.post("/{id}/approval", response_model=ApprovalDecisionResponse)
def submit_approval_decision(
    id: UUID,
    request: ApprovalDecisionRequest,
    db: Session = Depends(get_db),
):
    # Atomic transaction: verify status == NEEDS_REVIEW, verify version lock, update status, insert approval row
    run, approval = process_approval_decision(
        db=db,
        workflow_run_id=id,
        content_version_id=request.content_version_id,
        decision=request.decision,
        feedback=request.feedback,
    )

    # The resume job was queued atomically with the decision (process_approval_decision).

    return ApprovalDecisionResponse(
        workflow_run_id=run.id,
        approval_id=approval.id,
        content_version_id=approval.content_version_id,
        status=run.status,
        decision=approval.status,
        feedback=approval.feedback,
    )


class DraftEditRequest(BaseModel):
    title: str | None = Field(default=None, max_length=300)
    body: str = Field(min_length=1, max_length=20000)


@router.post("/{id}/draft/versions", status_code=201)
def save_draft_edit(id: UUID, request: DraftEditRequest, db: Session = Depends(get_db)):
    """Saves a human edit as a new version. Only while the run is NEEDS_REVIEW."""
    from app.workflows.service import create_human_edit_version
    version = create_human_edit_version(db, id, request.title, request.body)
    return {
        "content_version_id": str(version.id),
        "version_number": version.version_number,
        "origin": version.origin.value,
    }


@router.get("/{id}/research", response_model=ResearchResponse)
def read_research(
    id: UUID,
    db: Session = Depends(get_db),
):
    research = get_research_for_workflow_run(db, id)
    return ResearchResponse(
        id=research.id,
        workflow_run_id=research.workflow_run_id,
        summary=research.summary,
        findings=research.findings,
        sources=research.sources,
        created_at=research.created_at,
    )


@router.get("/{id}/brief", response_model=ContentBriefResponse)
def read_content_brief(
    id: UUID,
    db: Session = Depends(get_db),
):
    brief = get_brief_for_workflow_run(db, id)
    return ContentBriefResponse(
        id=brief.id,
        workflow_run_id=brief.workflow_run_id,
        brief=brief.brief,
        created_at=brief.created_at,
    )


@router.get("/{id}/draft", response_model=ContentDraftResponse)
def read_content_draft(
    id: UUID,
    db: Session = Depends(get_db),
):
    from app.strategies.models import ContentStrategy
    from app.workflows.models import WorkflowRun
    from app.workflows.draft_lint import lint_draft

    content, versions = get_draft_for_workflow_run(db, id)
    run = db.query(WorkflowRun).filter(WorkflowRun.id == id).first()
    voice_sample = None
    if run and run.strategy_id:
        strat = db.query(ContentStrategy).filter(ContentStrategy.id == run.strategy_id).first()
        if strat and strat.config:
            voice_sample = strat.config.get("voice_sample")

    from app.publishing.render import render_for_linkedin

    current_ver = versions[0]
    current_lint = lint_draft(current_ver.body, voice_sample=voice_sample)
    current_preview, current_trunc = render_for_linkedin(current_ver.title, current_ver.body)

    version_summaries = []
    for v in versions:
        v_preview, v_trunc = render_for_linkedin(v.title, v.body)
        version_summaries.append(
            ContentVersionSummary(
                id=v.id,
                version_number=v.version_number,
                origin=v.origin.value,
                title=v.title,
                body=v.body,
                lint_warnings=lint_draft(v.body, voice_sample=voice_sample),
                created_at=v.created_at,
                linkedin_preview=v_preview,
                char_count=len(v_preview),
                will_truncate=v_trunc,
            )
        )

    return ContentDraftResponse(
        content_id=content.id,
        workflow_run_id=content.workflow_run_id,
        current_version=ContentVersionSummary(
            id=current_ver.id,
            version_number=current_ver.version_number,
            origin=current_ver.origin.value,
            title=current_ver.title,
            body=current_ver.body,
            lint_warnings=current_lint,
            created_at=current_ver.created_at,
            linkedin_preview=current_preview,
            char_count=len(current_preview),
            will_truncate=current_trunc,
        ),
        versions=version_summaries,
        lint_warnings=current_lint,
        linkedin_preview=current_preview,
        char_count=len(current_preview),
        will_truncate=current_trunc,
    )


@router.get("/{id}/publication", response_model=PublicationResponse)
def read_workflow_run_publication(
    id: UUID,
    db: Session = Depends(get_db),
):
    """
    Get the publication record associated with this workflow run.
    """
    from app.content.models import Content, ContentVersion
    from app.publishing.models import Publication
    from fastapi import HTTPException, status

    content = db.query(Content).filter(Content.workflow_run_id == id).first()
    if not content:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No content found for workflow run {id}."
        )

    version_ids = [v.id for v in db.query(ContentVersion.id).filter(ContentVersion.content_id == content.id).all()]
    publication = (
        db.query(Publication)
        .filter(Publication.content_version_id.in_(version_ids))
        .order_by(Publication.created_at.desc())
        .first()
    )
    if not publication:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No publication found for workflow run {id}."
        )

    from app.scheduler.service import get_publication_sync_schedule_info
    from app.analytics.status import build_analytics_status
    from app.publishing.schemas import PublicationResponse
    schedule_info = get_publication_sync_schedule_info(db, publication)
    analytics_status = build_analytics_status(db, publication)

    return PublicationResponse(
        id=publication.id,
        content_version_id=publication.content_version_id,
        platform=publication.platform,
        status=publication.status,
        idempotency_key=publication.idempotency_key,
        external_id=publication.external_id,
        url=publication.url,
        publication_metadata=publication.publication_metadata,
        error=publication.error,
        created_at=publication.created_at,
        published_at=publication.published_at,
        schedule_info=schedule_info,
        analytics_status=analytics_status,
    )

