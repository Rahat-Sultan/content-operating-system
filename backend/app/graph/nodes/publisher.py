import logging
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.graph.state import ContentGraphState
from app.publishing.service import PublishingService
from app.publishing.models import PublicationStatus
from app.workflows.models import WorkflowRun, WorkflowRunStatus

logger = logging.getLogger(__name__)


def publisher_node(state: ContentGraphState) -> dict:
    """
    Publisher node in the Content Graph:
    1. Reads current_content_version_id and workflow_run_id from state.
    2. Uses PublishingService to atomically execute idempotent publication.
    3. Handles version validation, PostgreSQL uniqueness, and bounded retries.
    4. Transitions WorkflowRun status to PUBLISHING during attempt, and keeps state compact.
    5. Returns updated state containing publication_id.
    """
    content_version_id = state.get("current_content_version_id")
    workflow_run_id = state.get("workflow_run_id")

    if not content_version_id or not workflow_run_id:
        raise ValueError(
            f"Cannot publish: missing current_content_version_id ({content_version_id}) "
            f"or workflow_run_id ({workflow_run_id}) in state."
        )

    db: Session = SessionLocal()
    try:
        # Update workflow run status to PUBLISHING
        run = db.query(WorkflowRun).filter(WorkflowRun.id == workflow_run_id).first()
        if run and run.status not in (WorkflowRunStatus.FAILED, WorkflowRunStatus.REJECTED):
            run.status = WorkflowRunStatus.PUBLISHING
            db.commit()

        service = PublishingService()
        publication = service.publish_content_version(
            db=db,
            workflow_run_id=workflow_run_id,
            content_version_id=content_version_id,
            platform="linkedin",
        )

        logger.info(
            "Publisher node successfully processed publication %s (status: %s, external_id: %s)",
            publication.id,
            publication.status.value,
            publication.external_id,
        )

        return {
            "publication_id": publication.id,
        }

    except Exception as exc:
        logger.error("Publisher node execution failed for run %s: %s", workflow_run_id, exc, exc_info=True)
        # Update workflow run to FAILED with error
        try:
            run = db.query(WorkflowRun).filter(WorkflowRun.id == workflow_run_id).first()
            if run:
                run.status = WorkflowRunStatus.FAILED
                run.error = f"Publishing failed: {type(exc).__name__}: {str(exc)}"
                db.commit()
        except Exception:
            db.rollback()
        raise
    finally:
        db.close()
