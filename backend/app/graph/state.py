from typing import TypedDict
from uuid import UUID


class ContentGraphState(TypedDict):
    workflow_run_id: UUID
    strategy_id: UUID
    idea_id: UUID  # required at start, never null

    research_id: UUID | None
    content_brief_id: UUID | None
    content_id: UUID | None
    current_content_version_id: UUID | None

    approval_status: str | None
    approval_feedback: str | None

    publication_id: UUID | None
    error: str | None
