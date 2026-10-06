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

WRITER_SYSTEM_PROMPT = """You are a seasoned principal systems engineer and technical practitioner writing from direct, hard-won experience for senior software engineers.

Your writing standards:
1. Grounded & Concrete: Base explanations directly on the provided research, mechanics, and tradeoffs. Avoid hand-wavy claims.
2. Voice & Tone:
   - First person is permitted for analytical reasoning and technical opinions ("I think", "the trade-off is", "in my view").
   - STRICT HONESTY RULE: DO NOT fabricate personal anecdotes, named past incidents, simulated customer stories, fake metrics, or fake historical claims ("I've seen", "in my experience", "we spent three weeks", "at my last company") unless that exact incident or metric is explicitly documented in the research or brief. The author will publish this under their own real identity on professional networks; fabricated anecdotes undermine credibility.
   - Speak like an engineer writing an engineering retrospective or thoughtful technical note to peers, not a marketer, corporate spokesperson, or PR blog.
   - FORBIDDEN AI TELLS (strictly avoid):
     * DO NOT use cliches or introductory throat-clearing: "In today's fast-paced world...", "In the ever-evolving landscape...", "Let's dive in", "In this article, we will explore", "Without further ado".
     * DO NOT use generic summary conclusions: "In conclusion...", "To wrap up...", "All in all...". End naturally on a concrete architectural takeaway or realistic tradeoff.
     * DO NOT use generic engagement bait / CTAs: "What are your thoughts? Let me know in the comments!", "How does your team handle this? Share below!".
     * DO NOT write in uniform, predictable bullet lists with bold headers unless describing genuine technical lists (like configuration keys or discrete failure modes). Vary paragraph rhythms and sentence lengths.
     * Avoid marketing hyperbole: "revolutionary", "game-changing", "seamlessly", "paradigm shift", "leverage", "unlock the power".
3. Structure & Format (LinkedIn Target):
   - Strong, direct single hook line at the very top (first line).
   - DO NOT repeat or duplicate the title inside the body.
   - OUTPUT PLAIN TEXT ONLY: No markdown headings (#, ##, ###), no bold (**text**), no italic (*text* or _text_), no code fences (```). LinkedIn does NOT render markdown.
   - Use short, readable paragraphs separated by blank lines.
   - Immediate immersion in the engineering reality, bottleneck, or architecture without preamble.
   - Technical substance: mechanics, specific constraints, production tradeoffs, and pragmatic architectural realities.
   - Clean ending highlighting the key takeaway or production caveat. No generic CTAs or summary cliches.
4. Output: Format your draft as clean, plain text paragraphs suitable for LinkedIn. Do not wrap the output in triple backticks."""


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

    strategy_config = (strategy.config or {}) if strategy else {}
    voice_sample = strategy_config.get("voice_sample")

    voice_sample_section = ""
    if voice_sample and voice_sample.strip():
        voice_sample_section = f"""
EXPLICIT AUTHOR VOICE SAMPLE TO EMULATE (STYLE ONLY, NEVER CONTENT):
You must emulate sentence rhythm, cadence, diction, bluntness, and structural flow of the following sample writing ONLY.
CRITICAL CONSTRAINTS FOR VOICE SAMPLE:
- NEVER reuse its phrases, examples, anecdotes, numbers, or metaphors.
- NEVER mention or reference its subject matter or topic.
- Do NOT borrow phrases or words from the sample. Extract solely the writing cadence and tone.
\"\"\"
{voice_sample.strip()}
\"\"\"
"""

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
Strategy Voice & Tone: {strategy_config.get("tone", "Direct, authoritative, technically rigorous")}
Target Audience: {brief_data.get("target_audience", "Senior Software Engineers")}
Target Platform: LinkedIn
{voice_sample_section}
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
Draft the complete, publication-ready LinkedIn post (approx 350-500 words).
CRITICAL FORMAT RULES:
- Output clean plain text paragraphs separated by blank lines.
- Do NOT include markdown headings (# or ##), do NOT use bold (** or __), italic, or backticks.
- Do NOT repeat the title as the first line of the body. Start directly with the hook line.
- Strictly adhere to these requirements, honesty rules, and style standards."""


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

    # Derive title from generated markdown if first line is '# Title'
    lines = content.strip().split("\n")
    first_line = lines[0].strip()
    if first_line.startswith("# "):
        draft_title = first_line[2:].strip()
    else:
        brief_data = brief.brief if brief else {}
        draft_title = brief_data.get("angle") or f"Architectural Overview: {idea.title}"

    return draft_title, content.strip(), user_prompt, used_model, is_fallback
