import logging
from datetime import datetime, timezone
from uuid import UUID
from typing import Any
import psycopg
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import RetryPolicy, Command

from app.config import settings
from app.db import SessionLocal
from app.graph.nodes.research import research_node
from app.graph.nodes.brief import brief_node
from app.graph.nodes.writer import writer_node
from app.graph.nodes.approval import approval_node, route_approval_decision
from app.graph.nodes.publisher import publisher_node
from app.graph.state import ContentGraphState
from app.workflows.models import WorkflowRun, WorkflowRunStatus

logger = logging.getLogger(__name__)


def build_content_graph():
    """
    Full V0 Production Content Graph Topology:
    START -> research -> brief -> writer -> approval
                                              |
                   +--------------------------+--------------------------+
                REJECT                     REVISION                   APPROVE
                   |                          |                          |
                  END                       writer                   publisher
                                                                         |
                                                                        END
    """
    builder = StateGraph(ContentGraphState)

    # Attach nodes with transient retry policies for external LLM calls
    research_retry = RetryPolicy(max_attempts=2)
    brief_retry = RetryPolicy(max_attempts=2)
    writer_retry = RetryPolicy(max_attempts=2)

    builder.add_node("research", research_node, retry_policy=research_retry)
    builder.add_node("brief", brief_node, retry_policy=brief_retry)
    builder.add_node("writer", writer_node, retry_policy=writer_retry)
    builder.add_node("approval", approval_node)
    builder.add_node("publisher", publisher_node)

    # Edges
    builder.add_edge(START, "research")
    builder.add_edge("research", "brief")
    builder.add_edge("brief", "writer")
    builder.add_edge("writer", "approval")

    # Conditional routing from approval
    builder.add_conditional_edges(
        "approval",
        route_approval_decision,
        {
            "writer": "writer",
            "publisher": "publisher",
            "__end__": END,
        }
    )

    # Edge from publisher to END
    builder.add_edge("publisher", END)

    return builder


def get_postgres_connection_string() -> str:
    return settings.database_url.replace("postgresql+psycopg://", "postgresql://")


def get_content_graph():
    """
    Compiles content graph with PostgresSaver using settings.database_url.
    Connection is managed with autocommit=True per PostgresSaver requirements.
    """
    conn_string = get_postgres_connection_string()
    conn = psycopg.connect(conn_string, autocommit=True)
    checkpointer = PostgresSaver(conn)
    checkpointer.setup()
    return build_content_graph().compile(checkpointer=checkpointer)


def run_workflow_graph_background(workflow_run_id_str: str, strategy_id_str: str, idea_id_str: str):
    """
    Background worker function to execute the graph for a newly launched WorkflowRun.
    Executes from START until an interrupt() (e.g. approval) or terminal node.
    """
    run_id = UUID(workflow_run_id_str)
    strat_id = UUID(strategy_id_str)
    id_id = UUID(idea_id_str)

    config = {"configurable": {"thread_id": workflow_run_id_str}}
    initial_state = {
        "workflow_run_id": run_id,
        "strategy_id": strat_id,
        "idea_id": id_id,
        "research_id": None,
        "content_brief_id": None,
        "content_id": None,
        "current_content_version_id": None,
        "approval_status": None,
        "approval_feedback": None,
        "publication_id": None,
        "error": None,
    }

    db = SessionLocal()
    try:
        # Mark run as RUNNING in DB
        run = db.query(WorkflowRun).filter(WorkflowRun.id == run_id).first()
        if run and run.status == WorkflowRunStatus.PENDING:
            run.status = WorkflowRunStatus.RUNNING
            db.commit()

        # Execute graph stream
        conn_string = get_postgres_connection_string()
        with psycopg.connect(conn_string, autocommit=True) as conn:
            checkpointer = PostgresSaver(conn)
            checkpointer.setup()
            app = build_content_graph().compile(checkpointer=checkpointer)

            for _ in app.stream(initial_state, config):
                pass

            # Inspect state after stream pauses or finishes
            state = app.get_state(config)
            run = db.query(WorkflowRun).filter(WorkflowRun.id == run_id).first()
            if run:
                if state.next:  # Paused at interrupt (e.g. approval)
                    run.status = WorkflowRunStatus.NEEDS_REVIEW
                    db.commit()
                elif run.status not in (WorkflowRunStatus.FAILED, WorkflowRunStatus.CANCELLED, WorkflowRunStatus.REJECTED):
                    run.status = WorkflowRunStatus.COMPLETED
                    run.resolved_at = datetime.now(timezone.utc)
                    db.commit()

    except Exception as exc:
        logger.error("Background graph run %s failed: %s", workflow_run_id_str, exc, exc_info=True)
        try:
            run = db.query(WorkflowRun).filter(WorkflowRun.id == run_id).first()
            if run:
                run.status = WorkflowRunStatus.FAILED
                run.error = f"Workflow graph execution failed: {type(exc).__name__}: {str(exc)}"
                run.resolved_at = datetime.now(timezone.utc)
                db.commit()
        except Exception:
            db.rollback()
    finally:
        db.close()


def resume_workflow_graph_background(workflow_run_id_str: str, decision_data: dict[str, Any]):
    """
    Background worker function to resume a paused graph with the human approval decision.
    """
    run_id = UUID(workflow_run_id_str)
    config = {"configurable": {"thread_id": workflow_run_id_str}}

    db = SessionLocal()
    try:
        conn_string = get_postgres_connection_string()
        with psycopg.connect(conn_string, autocommit=True) as conn:
            checkpointer = PostgresSaver(conn)
            checkpointer.setup()
            app = build_content_graph().compile(checkpointer=checkpointer)

            # Resume with Command(resume=decision_data)
            for _ in app.stream(Command(resume=decision_data), config):
                pass

            # Inspect new state after resume
            state = app.get_state(config)
            run = db.query(WorkflowRun).filter(WorkflowRun.id == run_id).first()
            if run:
                if state.next:  # Paused again (e.g. after revision loop returns to approval)
                    run.status = WorkflowRunStatus.NEEDS_REVIEW
                    db.commit()
                else:  # Reached END
                    if decision_data.get("decision") == "REJECTED":
                        run.status = WorkflowRunStatus.REJECTED
                    elif run.status not in (WorkflowRunStatus.FAILED, WorkflowRunStatus.CANCELLED):
                        run.status = WorkflowRunStatus.COMPLETED
                    run.resolved_at = datetime.now(timezone.utc)
                    db.commit()

    except Exception as exc:
        logger.error("Background resume for run %s failed: %s", workflow_run_id_str, exc, exc_info=True)
        try:
            run = db.query(WorkflowRun).filter(WorkflowRun.id == run_id).first()
            if run:
                run.status = WorkflowRunStatus.FAILED
                run.error = f"Workflow resume execution failed: {type(exc).__name__}: {str(exc)}"
                run.resolved_at = datetime.now(timezone.utc)
                db.commit()
        except Exception:
            db.rollback()
    finally:
        db.close()
