import json
import logging
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.ideas.models import Idea
from app.llm.openrouter_client import (
    execute_llm_completion,
)
from app.strategies.models import ContentStrategy
from app.workflows.models import ContentBrief, Research

logger = logging.getLogger(__name__)

WRITER_SYSTEM_PROMPT = """You are a principal technical author and systems architect writing a deep, authoritative publication for senior software engineers.

Your writing standards:
1. Grounded & Concrete: Base explanations directly on the provided research and brief.
2. Tone: Authoritative, pragmatic, direct, and technically rigorous. Avoid fluff, hyperbolic marketing buzzwords ("revolutionary", "game-changing"), and generic introductory pleasantries.
3. Structure:
   - Strong title starting with a clear headline.
   - Compelling technical opening that frames the core problem and real failure modes.
   - Comprehensive architectural deep dive with system mechanics, tradeoffs, and code/design patterns.
   - Actionable takeaways or implementation checklists.
4. Output Markdown: Format your draft in clean, standard GitHub-flavored Markdown. Do not wrap the entire output in triple backticks."""


def build_writer_prompt(
    idea: Idea,
    strategy: ContentStrategy | None,
    research: Research | None,
    brief: ContentBrief | None,
    version_number: int,
    approval_feedback: str | None = None,
) -> str:
    brief_data = brief.brief if brief else {}
    research_summary = research.summary if research else "N/A"
    findings = (research.findings or {}) if research else {}
    key_findings = findings.get("key_findings", [])
    claims = findings.get("important_claims", [])

    revision_instructions = ""
    if version_number > 1 and approval_feedback:
        revision_instructions = f"""
CRITICAL REVISION INSTRUCTIONS (Version {version_number}):
The human reviewer requested revisions with the following specific feedback:
\"\"\"{approval_feedback}\"\"\"

You MUST explicitly address and incorporate this feedback into the new draft.
Do NOT just re-run the previous text unchanged — adapt the tone, structure, or content specifically to satisfy the reviewer's instructions.
"""

    return f"""Target Strategy: {strategy.name if strategy else "Engineering"}
Strategy Voice & Tone: {(strategy.config.get("tone") if strategy and strategy.config else "Direct, authoritative, technically rigorous")}
Target Audience: {brief_data.get("target_audience", "Senior Software Engineers")}

Idea Title: {idea.title}
Editorial Angle: {brief_data.get("angle", idea.title)}
Opening Hook: {brief_data.get("hook", "Architectural exploration")}
Key Points to Cover: {json.dumps(brief_data.get("key_points", []))}
Planned Structure: {json.dumps(brief_data.get("structure", {}))}

Grounding Research Summary:
{research_summary}

Grounded Research Findings:
- Key Findings: {json.dumps(key_findings)}
- Verified Claims: {json.dumps(claims)}
{revision_instructions}
Draft the complete, publication-ready technical article (minimum 400-600 words) adhering strictly to these requirements."""


def execute_writer_generation(
    db: Session,
    idea_id: UUID,
    strategy_id: UUID,
    research_id: UUID | None,
    content_brief_id: UUID | None,
    version_number: int,
    approval_feedback: str | None = None,
) -> tuple[str, str, str, str | None, bool]:
    """
    Executes real draft generation for an Idea.
    Returns: (draft_title, draft_body, raw_prompt, used_model, is_fallback)
    """
    idea = db.query(Idea).filter(Idea.id == idea_id).first()
    strategy = db.query(ContentStrategy).filter(ContentStrategy.id == strategy_id).first()
    research = db.query(Research).filter(Research.id == research_id).first() if research_id else None
    brief = db.query(ContentBrief).filter(ContentBrief.id == content_brief_id).first() if content_brief_id else None

    user_prompt = build_writer_prompt(
        idea=idea,
        strategy=strategy,
        research=research,
        brief=brief,
        version_number=version_number,
        approval_feedback=approval_feedback,
    )

    success, content, used_model, is_fallback = execute_llm_completion(
        system_prompt=WRITER_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        operation_name="Writer Generation",
        temperature=0.4,
    )

    if not success or not content.strip():
        logger.error("Writer LLM call failed or key invalid. Raising RuntimeError to trigger RetryPolicy.")
        raise RuntimeError(f"OpenRouter writer generation failed or key invalid for idea '{idea.title}'")

    # Derive title from generated markdown if first line is '# Title'
    lines = content.strip().split("\n")
    first_line = lines[0].strip()
    if first_line.startswith("# "):
        draft_title = first_line[2:].strip()
    else:
        brief_data = brief.brief if brief else {}
        draft_title = brief_data.get("angle") or f"Architectural Overview: {idea.title}"

    return draft_title, content.strip(), user_prompt, used_model, is_fallback
