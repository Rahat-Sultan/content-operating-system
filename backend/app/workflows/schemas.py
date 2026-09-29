from datetime import datetime
from uuid import UUID
from typing import Any
from pydantic import BaseModel, ConfigDict
from app.workflows.models import WorkflowRunStatus
from app.content.models import ApprovalStatus


class CreateWorkflowRunRequest(BaseModel):
    strategy_id: UUID
    idea_id: UUID


class WorkflowRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    workflow_run_id: UUID
    strategy_id: UUID
    idea_id: UUID
    status: WorkflowRunStatus
    error: str | None = None
    created_at: datetime
    resolved_at: datetime | None = None


class ApprovalDecisionRequest(BaseModel):
    content_version_id: UUID
    decision: ApprovalStatus
    feedback: str | None = None


class ApprovalDecisionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    workflow_run_id: UUID
    approval_id: UUID
    content_version_id: UUID
    status: WorkflowRunStatus
    decision: ApprovalStatus
    feedback: str | None = None


class ResearchResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workflow_run_id: UUID
    summary: str | None = None
    findings: dict[str, Any]
    sources: dict[str, Any]
    created_at: datetime


class ContentBriefResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workflow_run_id: UUID
    brief: dict[str, Any]
    created_at: datetime
