from uuid import UUID
from fastapi import APIRouter, BackgroundTasks, Depends
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
from app.graph.content_graph import (
    run_workflow_graph_background,
    resume_workflow_graph_background,
)

router = APIRouter(prefix="/workflow-runs", tags=["workflow-runs"])


@router.post("", response_model=WorkflowRunResponse, status_code=200)
def start_workflow_run(
    request: CreateWorkflowRunRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    run = create_workflow_run(
        db=db,
        strategy_id=request.strategy_id,
        idea_id=request.idea_id,
    )

    # Launch graph asynchronously in background via FastAPI BackgroundTasks
    background_tasks.add_task(
        run_workflow_graph_background,
        str(run.id),
        str(run.strategy_id),
        str(run.idea_id),
    )

    return WorkflowRunResponse(
        workflow_run_id=run.id,
        strategy_id=run.strategy_id,
        idea_id=run.idea_id,
        status=run.status,
        error=run.error,
        created_at=run.created_at,
        resolved_at=run.resolved_at,
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
    )


@router.post("/{id}/approval", response_model=ApprovalDecisionResponse)
def submit_approval_decision(
    id: UUID,
    request: ApprovalDecisionRequest,
    background_tasks: BackgroundTasks,
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

    # Resume graph execution in background
    decision_payload = {
        "decision": request.decision.value,
        "feedback": request.feedback,
    }
    background_tasks.add_task(
        resume_workflow_graph_background,
        str(run.id),
        decision_payload,
    )

    return ApprovalDecisionResponse(
        workflow_run_id=run.id,
        approval_id=approval.id,
        content_version_id=approval.content_version_id,
        status=run.status,
        decision=approval.status,
        feedback=approval.feedback,
    )


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
    content, versions = get_draft_for_workflow_run(db, id)
    current_ver = versions[0]
    return ContentDraftResponse(
        content_id=content.id,
        workflow_run_id=content.workflow_run_id,
        current_version=ContentVersionSummary(
            id=current_ver.id,
            version_number=current_ver.version_number,
            origin=current_ver.origin.value,
            title=current_ver.title,
            body=current_ver.body,
            created_at=current_ver.created_at,
        ),
        versions=[
            ContentVersionSummary(
                id=v.id,
                version_number=v.version_number,
                origin=v.origin.value,
                title=v.title,
                body=v.body,
                created_at=v.created_at,
            )
            for v in versions
        ],
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

    return publication

