import logging
from typing import Literal
from langgraph.types import interrupt
from app.graph.state import ContentGraphState

logger = logging.getLogger(__name__)


def approval_node(state: ContentGraphState) -> dict:
    """
    Approval node (human-in-the-loop interrupt boundary):
    - Minimal side effects before interrupt().
    - Interrupts execution with payload identifying the content version awaiting review.
    - On resume, receives decision dict:
        {"decision": "APPROVED" | "REVISION_REQUESTED" | "REJECTED", "feedback": "..."}
    - Returns updated state keys (approval_status, approval_feedback).
    - Note: Database insertion of the Approval record is handled atomically in the API layer
      before triggering resume.
    """
    current_content_version_id = state.get("current_content_version_id")
    workflow_run_id = state["workflow_run_id"]

    logger.info(
        "Approval node pausing at interrupt for run %s, version %s",
        workflow_run_id,
        current_content_version_id,
    )

    # Interrupt execution; wait for external resume Command
    decision_payload = interrupt({
        "workflow_run_id": str(workflow_run_id),
        "content_version_id": str(current_content_version_id) if current_content_version_id else None,
        "message": "Human approval required for draft version."
    })

    # On resume, process human decision
    logger.info("Approval node resumed with decision: %s", decision_payload)
    if isinstance(decision_payload, dict):
        status = decision_payload.get("decision")
        feedback = decision_payload.get("feedback")
    else:
        status = str(decision_payload)
        feedback = None

    return {
        "approval_status": status,
        "approval_feedback": feedback,
    }


def route_approval_decision(state: ContentGraphState) -> Literal["writer", "publisher", "__end__"]:
    """
    Conditional routing edge after approval:
    - REVISION_REQUESTED -> routes back to writer
    - APPROVED -> routes to publisher
    - REJECTED (or anything else) -> routes to END
    """
    status = state.get("approval_status")
    if status == "REVISION_REQUESTED":
        return "writer"
    if status == "APPROVED":
        return "publisher"
    return "__end__"

