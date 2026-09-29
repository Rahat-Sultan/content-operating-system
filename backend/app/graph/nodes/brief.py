import logging
from datetime import datetime, timezone
from uuid import uuid4

from app.db import SessionLocal
from app.graph.state import ContentGraphState
from app.ideas.models import Idea
from app.workflows.models import ContentBrief, Research, WorkflowRun, WorkflowRunStatus
from app.workflows.brief_provider import execute_brief_generation

logger = logging.getLogger(__name__)


def brief_node(state: ContentGraphState) -> dict:
    """
    Strategist / Content Brief node:
    - Reads research_id and idea_id from graph state.
    - Loads the Research record and Idea from Postgres.
    - Calls the brief provider stub.
    - Persists a new row in content_briefs table.
    - Returns {"content_brief_id": brief_record.id}.
    - On failure, updates workflow_runs.status = 'FAILED' and raises exc.
    """
    workflow_run_id = state["workflow_run_id"]
    research_id = state.get("research_id")
    idea_id = state["idea_id"]

    db = SessionLocal()
    try:
        idea = db.query(Idea).filter(Idea.id == idea_id).first()
        topic = idea.title if idea else "Untitled Topic"

        research = None
        if research_id:
            research = db.query(Research).filter(Research.id == research_id).first()
        research_summary = research.summary if research else None

        # Call brief generator stub
        brief_data = execute_brief_generation(query=topic, research_summary=research_summary)

        # Persist content_briefs row (one per workflow run)
        brief_record = db.query(ContentBrief).filter(ContentBrief.workflow_run_id == workflow_run_id).first()
        if not brief_record:
            brief_record = ContentBrief(
                id=uuid4(),
                workflow_run_id=workflow_run_id,
                brief=brief_data,
            )
            db.add(brief_record)
        else:
            brief_record.brief = brief_data

        db.commit()
        db.refresh(brief_record)

        logger.info(
            "Brief node successfully created/updated content_brief %s for run %s",
            brief_record.id,
            workflow_run_id,
        )
        return {
            "content_brief_id": brief_record.id,
            "error": None,
        }

    except Exception as exc:
        db.rollback()
        err_msg = f"Brief node failed: {type(exc).__name__}: {str(exc)}"
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
