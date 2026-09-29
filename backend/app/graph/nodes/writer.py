import logging
from datetime import datetime, timezone
from uuid import uuid4

from app.db import SessionLocal
from app.graph.state import ContentGraphState
from app.workflows.models import ContentBrief, WorkflowRun, WorkflowRunStatus
from app.content.models import Content, ContentVersion, ContentVersionOrigin

logger = logging.getLogger(__name__)


def writer_node(state: ContentGraphState) -> dict:
    """
    Writer node:
    - Reads content_brief_id from graph state.
    - Loads ContentBrief from Postgres.
    - Determines version number:
      If content row exists, version_number = max(existing_versions) + 1.
      Otherwise, creates new content row with version_number = 1.
    - Inserts a new immutable ContentVersion row with origin=WRITER_AGENT.
    - Updates WorkflowRun status to NEEDS_REVIEW when ready for human review.
    - Returns {"content_id": ..., "current_content_version_id": ...}.
    """
    workflow_run_id = state["workflow_run_id"]
    content_brief_id = state.get("content_brief_id")
    approval_feedback = state.get("approval_feedback")

    db = SessionLocal()
    try:
        brief_record = None
        if content_brief_id:
            brief_record = db.query(ContentBrief).filter(ContentBrief.id == content_brief_id).first()

        brief_dict = brief_record.brief if brief_record else {}
        angle = brief_dict.get("angle", "Technical architecture overview")
        hook = brief_dict.get("hook", "Key engineering insights")
        target_audience = brief_dict.get("target_audience", "Engineers")

        # 1. Get or create logical Content container
        content_row = db.query(Content).filter(Content.workflow_run_id == workflow_run_id).first()
        if not content_row:
            content_row = Content(
                id=uuid4(),
                workflow_run_id=workflow_run_id,
            )
            db.add(content_row)
            db.flush()
            version_number = 1
        else:
            # Determine next version number
            latest_version = (
                db.query(ContentVersion)
                .filter(ContentVersion.content_id == content_row.id)
                .order_by(ContentVersion.version_number.desc())
                .first()
            )
            version_number = (latest_version.version_number + 1) if latest_version else 1

        # 2. Construct draft body
        revision_clause = ""
        if version_number > 1 and approval_feedback:
            revision_clause = f"\n\n### Revision Notes Incorporated:\n* Reviewer feedback addressed: '{approval_feedback}'"

        draft_title = f"Architectural Overview: {angle}"
        draft_body = (
            f"# {draft_title}\n\n"
            f"> **STUB DRAFT (v{version_number})** — Generated for {target_audience}.\n\n"
            f"**Hook:** {hook}\n\n"
            f"## Overview\n"
            f"This draft demonstrates durable state management in content production pipelines. "
            f"State is checkpointed durably in PostgreSQL to survive process termination.{revision_clause}\n\n"
            f"## Actionable Takeaways\n"
            f"- Verify database invariants before code execution.\n"
            f"- Keep graph state small and store domain entities in primary tables.\n"
            f"- Human approval is an explicit interrupt boundary.\n"
        )

        # 3. Insert immutable ContentVersion
        version_record = ContentVersion(
            id=uuid4(),
            content_id=content_row.id,
            version_number=version_number,
            origin=ContentVersionOrigin.WRITER_AGENT,
            title=draft_title,
            body=draft_body,
        )
        db.add(version_record)

        # 4. Mark workflow_runs status as NEEDS_REVIEW
        run = db.query(WorkflowRun).filter(WorkflowRun.id == workflow_run_id).first()
        if run:
            run.status = WorkflowRunStatus.NEEDS_REVIEW

        db.commit()
        db.refresh(version_record)

        logger.info(
            "Writer node created ContentVersion v%d (%s) for run %s. Status set to NEEDS_REVIEW.",
            version_number,
            version_record.id,
            workflow_run_id,
        )
        return {
            "content_id": content_row.id,
            "current_content_version_id": version_record.id,
            "error": None,
        }

    except Exception as exc:
        db.rollback()
        err_msg = f"Writer node failed: {type(exc).__name__}: {str(exc)}"
        logger.error(err_msg, exc_info=True)

        try:
            run = db.query(WorkflowRun).filter(WorkflowRun.id == workflow_run_id).first()
            if run:
                run.status = WorkflowRunStatus.FAILED
                run.error = err_msg
                run.resolved_at = datetime.now(timezone.utc)
                db.commit()
        except Exception as persist_err:
            logger.error("Failed to persist failure status to workflow_run: %s", persist_err)
            db.rollback()

        raise exc

    finally:
        db.close()
