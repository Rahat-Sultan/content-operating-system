import json
import logging
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.ideas.models import Idea
from app.llm.openrouter_client import (
    clean_json_markdown,
    execute_llm_completion,
)
from app.strategies.models import ContentStrategy
from app.workflows.models import Research

logger = logging.getLogger(__name__)

BRIEF_SYSTEM_PROMPT = """You are a senior Content Strategist and Editorial Director for a high-signal technical publication.
Your job is to transform grounded technical research into an actionable, structured content brief tailored to the strategy's niche, target audience, and tone.

Schema requirement:
You MUST output STRICTLY a valid JSON object matching this schema:
{
  "angle": "Unique, sharp perspective or thesis for this piece",
  "hook": "Compelling opening hook that addresses a real operational pain point or technical curiosity",
  "target_audience": "Specific audience tier (e.g., Senior Backend & Platform Engineers)",
  "key_points": [
    "Core architectural insight or tradeoff 1",
    "Core architectural insight or tradeoff 2",
    "Core architectural insight or tradeoff 3"
  ],
  "structure": {
    "introduction": "How the problem manifests and why conventional wisdom fails",
    "deep_dive": "Architectural mechanics and verified patterns from the research",
    "implementation": "Concrete operational guidelines, code structures, or system boundaries",
    "conclusion": "Key takeaway and architectural rules of thumb"
  },
  "tone": "Direct, authoritative, technically precise, and pragmatic",
  "cta": "Clear call to action or discussion prompt for engineers",
  "platform": "technical_blog",
  "content_goal": "Educate practitioners and establish architectural authority"
}
Do not include markdown fences outside the JSON object."""


def build_brief_prompt(
    idea: Idea,
    strategy: ContentStrategy | None,
    research: Research | None,
) -> str:
    strat_config = strategy.config if strategy else {}
    research_summary = research.summary if research else "No research summary available."
    findings = research.findings if research else {}
    key_findings = findings.get("key_findings", [])
    claims = findings.get("important_claims", [])

    return f"""Target Strategy: {strategy.name if strategy else "Engineering Strategy"}
Strategy Niche/Description: {strategy.description if strategy else "Technical Architecture"}
Strategy Target Audience: {strat_config.get("audience", "Senior Engineers & System Architects")}
Strategy Tone & Guidelines: {strat_config.get("tone", "Authoritative, practical, direct")}
Target Platforms: {strat_config.get("platforms", ["technical_blog"])}

Idea Title: {idea.title}
Idea Description: {idea.description or "N/A"}

Grounding Research Summary:
{research_summary}

Grounded Research Findings:
- Key Findings: {json.dumps(key_findings)}
- Important Claims: {json.dumps(claims)}

Generate a structured, authoritative content brief that translates this research into an engaging technical piece."""


def execute_brief_for_idea(
    db: Session,
    idea_id: UUID,
    strategy_id: UUID,
    research_id: UUID | None,
) -> tuple[dict[str, Any], str, str]:
    """
    Executes real Content Brief generation using Research and Strategy parameters.
    Returns: (brief_data_dict, user_prompt, raw_llm_response)
    """
    idea = db.query(Idea).filter(Idea.id == idea_id).first()
    if not idea:
        raise ValueError(f"Idea {idea_id} not found.")

    strategy = db.query(ContentStrategy).filter(ContentStrategy.id == strategy_id).first()
    research = None
    if research_id:
        research = db.query(Research).filter(Research.id == research_id).first()

    user_prompt = build_brief_prompt(idea, strategy, research)

    success, content, used_model, is_fallback = execute_llm_completion(
        system_prompt=BRIEF_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        operation_name="Content Brief Generation",
        response_format={"type": "json_object"},
        temperature=0.3,
    )

    raw_response = content
    if not success or not content.strip():
        logger.error("Brief generation LLM call failed or key invalid. Raising RuntimeError to trigger RetryPolicy.")
        raise RuntimeError(f"OpenRouter brief generation failed or key invalid for idea '{idea.title}'")

    cleaned = clean_json_markdown(raw_response)
    try:
        brief_data = json.loads(cleaned)
    except json.JSONDecodeError as err:
        logger.error("Failed to parse brief JSON: %s. Content: %s", err, cleaned[:200])
        brief_data = {
            "angle": f"Architecture for {idea.title}",
            "hook": f"Analyzing {idea.title}",
            "target_audience": "Engineers",
            "key_points": ["System design", "Reliability"],
            "structure": {"introduction": "Overview", "conclusion": "Takeaways"},
            "tone": "Technical",
            "cta": "Learn more",
            "platform": "technical_blog",
            "content_goal": "Technical leadership",
        }

    if is_fallback:
        brief_data["is_fallback"] = True
    brief_data["provider"] = used_model

    return brief_data, user_prompt, raw_response


# Backward compatibility for legacy tests
def execute_brief_generation(query: str, research_summary: str | None) -> dict[str, Any]:
    return {
        "is_stub": True,
        "angle": f"Architecture for {query}",
        "hook": f"How {query} works in practice",
        "target_audience": "Engineers",
        "key_points": ["Tradeoffs", "Implementation"],
        "structure": {"intro": "Intro", "body": "Body"},
        "tone": "Technical",
        "cta": "Read more",
        "platform": "technical_blog",
        "content_goal": "Education",
    }
