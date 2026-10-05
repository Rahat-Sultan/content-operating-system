import json
import logging
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.ideas.models import Idea
from app.ideas.service import get_idea_sources
from app.llm.openrouter_client import (
    clean_json_markdown,
    execute_llm_completion,
)
from app.sources.models import SourceItem

logger = logging.getLogger(__name__)

RESEARCH_SYSTEM_PROMPT = """You are an expert technical researcher and systems analyst for an engineering publication.
Your goal is to analyze grounded source material and synthesize structured research findings and verified claims.

Rules:
1. ONLY synthesize claims, facts, and patterns grounded directly in the provided source material.
2. Do NOT invent quotes, data points, or conclusions beyond what the sources say.
3. Be specific, concrete, and technically rigorous.
4. Output STRICTLY a valid JSON object matching this schema:
{
  "summary": "2-3 paragraph detailed technical synthesis of the problem, architectural mechanics, and industry implications.",
  "findings": {
    "key_findings": [
      "Key technical insight 1 grounded in the source",
      "Key technical insight 2 grounded in the source",
      "Key technical insight 3 grounded in the source"
    ],
    "important_claims": [
      "Verifiable technical claim or architectural tradeoff stated in the source"
    ],
    "confidence": 0.95
  }
}
Do not include markdown fences outside the JSON object."""


def build_research_prompt(idea: Idea, source_items: list[SourceItem], item_groundings: dict[UUID, dict[str, Any]] | None = None) -> str:
    groundings = item_groundings or {}
    sources_text = []
    for idx, item in enumerate(source_items):
        item_g = groundings.get(item.id, {})
        has_full_content = item_g.get("grounded_content_used", False)
        content_text = (item_g.get("content") or item.content or "").strip()

        # Truncate very long content while keeping rich context
        if len(content_text) > 4000:
            content_text = content_text[:4000] + "... [truncated]"

        grounding_type = "Full Scraped Web Content" if has_full_content else "Feed Metadata/Summary"
        sources_text.append(
            f"Source [{idx + 1}] ({grounding_type}):\n"
            f"Title: {item.title}\n"
            f"URL: {item.url}\n"
            f"Content:\n{content_text}\n"
        )

    sources_block = "\n---\n".join(sources_text) if sources_text else "No attached source items."

    return f"""Target Idea Title: {idea.title}
Target Idea Description: {idea.description or "N/A"}

Grounding Source Material:
{sources_block}

Synthesize a comprehensive research brief evaluating the architectural patterns, challenges, and mechanisms discussed in the source material."""


def execute_research_for_idea(
    db: Session,
    idea_id: UUID,
) -> tuple[dict[str, Any], str, str]:
    """
    Executes real research synthesis for an Idea using its backing source items.
    Enriches grounding by fetching real page content via Scrapling (falling back to item description if fetch fails).
    Returns: (research_result_dict, user_prompt, raw_llm_response)
    
    If OpenRouter is unavailable or key is placeholder, falls back loudly with is_fallback: true.
    """
    from app.sources.content_fetcher import fetch_url_content

    idea = db.query(Idea).filter(Idea.id == idea_id).first()
    if not idea:
        raise ValueError(f"Idea {idea_id} not found in database.")

    source_items = get_idea_sources(db, idea_id)

    # Scrape real page content via Scrapling for each linked source item
    item_groundings: dict[UUID, dict[str, Any]] = {}
    sources_items_payload: list[dict[str, Any]] = []

    for item in source_items:
        scraped_content = ""
        fetch_method = "metadata"
        grounded_used = False

        meta = item.source_metadata or {}
        # Check cache on source_item first
        if meta.get("scraped_content"):
            scraped_content = meta["scraped_content"]
            fetch_method = meta.get("scraped_method", "cached")
            grounded_used = True
        elif item.url and item.url.startswith(("http://", "https://")):
            try:
                success, fetched_text, fetch_info = fetch_url_content(item.url, obey_robots=True)
                if success and fetched_text:
                    scraped_content = fetched_text
                    fetch_method = fetch_info.get("method", "plain_fetcher")
                    grounded_used = True
                    # Cache back onto source_item
                    new_meta = dict(meta)
                    new_meta["scraped_content"] = fetched_text
                    new_meta["scraped_method"] = fetch_method
                    item.source_metadata = new_meta
                    # Also populate content column if previously empty or short
                    if not item.content or len(item.content) < len(fetched_text):
                        item.content = fetched_text
                    db.add(item)
                    db.commit()
            except Exception as fetch_exc:
                logger.warning("Scrapling content fetch failed for source %s: %s", item.url, fetch_exc)

        effective_content = scraped_content or item.content or ""
        item_groundings[item.id] = {
            "content": effective_content,
            "grounded_content_used": grounded_used,
            "fetch_method": fetch_method,
        }

        sources_items_payload.append({
            "title": item.title or "Untitled Source",
            "url": item.url or "",
            "author": (item.source_metadata or {}).get("author") or "Unknown",
            "retrieved_at": item.collected_at.isoformat() if item.collected_at else None,
            "grounding_type": "scraped_content" if grounded_used else "metadata",
            "fetch_method": fetch_method,
        })

    sources_payload = {
        "items": sources_items_payload
    }

    user_prompt = build_research_prompt(idea, source_items, item_groundings)

    success, content, used_model, is_fallback = execute_llm_completion(
        system_prompt=RESEARCH_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        operation_name="Research Generation",
        response_format={"type": "json_object"},
        temperature=0.2,
    )

    raw_response = content
    cleaned = clean_json_markdown(raw_response)
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as err:
        logger.error("Failed to parse research JSON from model: %s. Content: %s", err, cleaned[:200])
        parsed = {
            "summary": f"Research on {idea.title}",
            "findings": {
                "key_findings": [cleaned[:200]],
                "important_claims": [],
                "confidence": 0.50,
            },
        }

    findings = parsed.get("findings", {})
    if is_fallback:
        findings["is_fallback"] = True
    findings["provider"] = used_model

    result = {
        "summary": parsed.get("summary", f"Research synthesis for {idea.title}"),
        "findings": findings,
        "sources": sources_payload,
    }

    return result, user_prompt, raw_response


# Backward compatibility for legacy tests
def execute_research_query(query: str) -> dict[str, Any]:
    return {
        "summary": f"Research overview for: {query}",
        "findings": {
            "is_stub": True,
            "key_findings": [f"Analysis on {query}"],
            "important_claims": ["Verified pipeline pattern"],
            "confidence": 0.85,
        },
        "sources": {
            "items": [{"title": f"Source for {query}", "url": "https://example.com"}]
        },
    }
