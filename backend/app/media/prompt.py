from uuid import UUID
from sqlalchemy.orm import Session

from app.content.models import Content, ContentVersion
from app.workflows.models import WorkflowRun, ContentBrief
from app.strategies.models import ContentStrategy


def construct_image_prompt(
    db: Session,
    content: Content,
    version: ContentVersion,
    user_override_prompt: str | None = None,
) -> str:
    """
    Constructs an image generation prompt synthesizing:
    Strategy + Content Brief + Content Version.
    """
    if user_override_prompt and user_override_prompt.strip():
        return user_override_prompt.strip()

    title = version.title or ""
    # Retrieve workflow run and strategy
    workflow_run = db.query(WorkflowRun).filter(WorkflowRun.id == content.workflow_run_id).first()
    strategy_name = ""
    target_audience = ""
    if workflow_run:
        strategy = db.query(ContentStrategy).filter(ContentStrategy.id == workflow_run.strategy_id).first()
        if strategy:
            strategy_name = strategy.name
            target_audience = strategy.config.get("target_audience", "")

    # Retrieve brief
    brief = db.query(ContentBrief).filter(ContentBrief.workflow_run_id == content.workflow_run_id).first()
    key_theme = ""
    if brief and isinstance(brief.brief, dict):
        key_theme = brief.brief.get("core_thesis") or brief.brief.get("angle") or brief.brief.get("key_takeaway") or ""

    # Synthesize prompt
    parts = []
    if title:
        parts.append(f"Editorial illustration for article: '{title}'")
    else:
        parts.append("Editorial technology illustration")

    if strategy_name:
        parts.append(f"Context: {strategy_name}")
    if target_audience:
        parts.append(f"Target audience: {target_audience}")
    if key_theme:
        parts.append(f"Visual theme: {key_theme}")

    prompt = ". ".join(parts) + ". Clean, modern, technical aesthetic, dark slate background, professional composition."
    return prompt
