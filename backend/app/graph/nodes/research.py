import logging
from datetime import datetime, timezone
from uuid import uuid4

from app.db import SessionLocal
from app.graph.state import ContentGraphState
from app.ideas.models import Idea
from app.workflows.models import Research, WorkflowRun, WorkflowRunStatus
from app.workflows.research_provider import execute_research_query

logger = logging.getLogger(__name__)


def research_node(state: ContentGraphState) -> dict:
    """
    Research node:
    - Reads idea_id from graph state.
    - Loads Idea (title/description) from Postgres.
    - Queries the external research provider (stub).
    - Persists the resulting Research record to PostgreSQL.
    - Returns updated state containing research_id.
    - If unhandled failure occurs, marks workflow_runs.status = 'FAILED' and sets error.
    """
    workflow_run_id = state["workflow_run_id"]
    idea_id = state["idea_id"]

    db = SessionLocal()
    try:
        # Load Idea
        idea = db.query(Idea).filter(Idea.id == idea_id).first()
        if not idea:
            raise ValueError(f"Idea with id {idea_id} not found in database.")

        query = idea.title
        if idea.description:
            query = f"{idea.title} - {idea.description}"

        # Call research provider
        results = execute_research_query(query)

        # Persist research artifact
        research_record = Research(
            id=uuid4(),
            workflow_run_id=workflow_run_id,
            summary=results.get("summary"),
            findings=results.get("findings", {}),
            sources=results.get("sources", {}),
        )
        db.add(research_record)

        # Update WorkflowRun status to RUNNING if it was PENDING
        run = db.query(WorkflowRun).filter(WorkflowRun.id == workflow_run_id).first()
        if run and run.status == WorkflowRunStatus.PENDING:
            run.status = WorkflowRunStatus.RUNNING

        db.commit()
        db.refresh(research_record)

        logger.info(
            "Research node successfully created research record %s for run %s",
            research_record.id,
            workflow_run_id,
        )
        return {
            "research_id": research_record.id,
            "error": None,
        }

    except Exception as exc:
        db.rollback()
        err_msg = f"Research node failed: {type(exc).__name__}: {str(exc)}"
        logger.error(err_msg, exc_info=True)

        # Persist terminal failure to workflow_runs table
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

        # Re-raise so LangGraph RetryPolicy can attempt retry or record error in checkpointer
        raise exc

    finally:
        db.close()
