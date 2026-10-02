import json
import logging
from typing import Any

from app.llm.openrouter_client import (
    clean_json_markdown,
    execute_llm_completion,
)

logger = logging.getLogger(__name__)

SCOUT_SCORING_SYSTEM_PROMPT = """You are an expert Content Scout & Evaluator for a technical content strategy.
Your goal is to analyze newly ingested source items and synthesize viable, high-impact content opportunities (ideas) aligned with the target strategy.

Evaluation Criteria (scores strictly between 0.000 and 1.000):
- relevance: Alignment with strategy topics, domains, and goals.
- trend: Timeliness, traction, and emergence in current industry discourse.
- novelty: Originality of angle, unique framing, or fresh insight rather than regurgitation.
- audience_fit: Suitability and depth for the defined target audience.
- source_quality: Authority, credibility, and technical rigor of the backing source items.

You MUST respond strictly with a valid JSON object matching this schema:
{
  "ideas": [
    {
      "title": "Clear, compelling idea headline",
      "description": "2-3 sentence overview of the angle, core thesis, and value proposition.",
      "relevance": 0.85,
      "trend": 0.75,
      "novelty": 0.80,
      "audience_fit": 0.90,
      "source_quality": 0.85,
      "rationale": "Detailed explanation reflecting the actual article content and why this topic fits the strategy.",
      "source_item_indices": [0]
    }
  ]
}
Only output the JSON object. Do not include markdown code blocks or additional text."""


def build_scout_prompt(strategy_name: str, strategy_config: dict[str, Any], items: list[dict[str, Any]]) -> str:
    items_text = []
    for idx, item in enumerate(items):
        title = item.get("title") or "Untitled"
        url = item.get("url") or ""
        desc = item.get("description") or ""
        items_text.append(f"[{idx}] Title: {title}\nURL: {url}\nSummary: {desc}\n")

    return f"""Target Strategy: {strategy_name}
Strategy Topics: {strategy_config.get("topics", [])}
Target Audience: {strategy_config.get("audience", "Technical Practitioners")}
Target Platforms: {strategy_config.get("platforms", [])}

New Source Items:
{chr(10).join(items_text)}

Identify up to 3 high-impact content ideas based on these source items and evaluate each across all 5 dimensions."""


def compute_final_score(rel: float, trend: float, nov: float, aud: float, qual: float) -> float:
    """
    Weighted final score computed strictly by application code per specification:
    0.30 * relevance + 0.20 * trend + 0.15 * novelty + 0.20 * audience_fit + 0.15 * source_quality
    """
    score = (0.30 * rel) + (0.20 * trend) + (0.15 * nov) + (0.20 * aud) + (0.15 * qual)
    return round(score, 3)


def execute_scout_and_score(
    strategy_name: str,
    strategy_config: dict[str, Any],
    items: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], str, str]:
    """
    Executes Scout + Scoring combined.
    Returns: (scored_ideas, raw_prompt, raw_llm_response)
    
    Fallback chain handled via app.llm.openrouter_client:
    1. Primary model: nvidia/nemotron-3-super-120b-a12b:free
    2. Secondary model: google/gemma-4-26b-a4b-it:free
    3. Fallback model: openrouter/free
    4. If none available or key is placeholder: Rule-based fallback evaluator
       with explicit "is_fallback": true in scoring_metadata and loud warning.
    """
    user_prompt = build_scout_prompt(strategy_name, strategy_config, items)

    success, content, used_model, is_fallback = execute_llm_completion(
        system_prompt=SCOUT_SCORING_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        operation_name="Scout & Scoring",
        response_format={"type": "json_object"},
        temperature=0.2,
    )

    raw_response = content if (success and content.strip()) else ""

    # Step 3: Rule-based fallback if no LLM responded or key missing/placeholder
    if not raw_response:
        check_api_key_configuration()
        is_fallback = True
        used_model = "rule-evaluator"
        logger.warning(
            "All OpenRouter calls failed or API key invalid. Using fallback evaluator with is_fallback: true."
        )
        ideas_data = []
        for idx, item in enumerate(items[:2]):
            title = item.get("title", "Tech Trend")
            ideas_data.append({
                "title": f"Architectural Deep-Dive: {title}",
                "description": f"Analysis of modern engineering patterns inspired by {title}, focusing on production resilience and scalability.",
                "relevance": 0.88,
                "trend": 0.82,
                "novelty": 0.79,
                "audience_fit": 0.91,
                "source_quality": 0.85,
                "rationale": f"Fallback rationale for '{title}' (API unavailable).",
                "source_item_indices": [idx],
            })
        raw_response = json.dumps({"ideas": ideas_data}, indent=2)

    cleaned = clean_json_markdown(raw_response)
    parsed = json.loads(cleaned)
    raw_ideas = parsed.get("ideas", [])

    scored_ideas: list[dict[str, Any]] = []
    for raw in raw_ideas:
        rel = float(raw.get("relevance", 0.7))
        trend = float(raw.get("trend", 0.7))
        nov = float(raw.get("novelty", 0.7))
        aud = float(raw.get("audience_fit", 0.7))
        qual = float(raw.get("source_quality", 0.7))

        final_score = compute_final_score(rel, trend, nov, aud, qual)

        scoring_meta: dict[str, Any] = {
            "rationale": raw.get("rationale", ""),
            "provider": used_model,
            "raw_scores": {
                "relevance": rel,
                "trend": trend,
                "novelty": nov,
                "audience_fit": aud,
                "source_quality": qual,
            },
        }
        if is_fallback:
            scoring_meta["is_fallback"] = True

        scored_ideas.append({
            "title": raw.get("title", "Untitled Opportunity"),
            "description": raw.get("description", ""),
            "relevance_score": rel,
            "trend_score": trend,
            "novelty_score": nov,
            "audience_fit_score": aud,
            "source_quality_score": qual,
            "final_score": final_score,
            "scoring_metadata": scoring_meta,
            "source_item_indices": raw.get("source_item_indices", []),
        })

    return scored_ideas, user_prompt, raw_response
