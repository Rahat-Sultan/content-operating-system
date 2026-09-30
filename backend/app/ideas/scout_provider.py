import json
import logging
import os
import re
from typing import Any
import httpx

from app.config import settings

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

# Model fallback chain per specification
PRIMARY_MODEL = "nvidia/nemotron-3-super-120b-a12b:free"
FALLBACK_MODEL = "openrouter/free"


def is_placeholder_key(key: str | None) -> bool:
    """Check if the API key is missing, empty, or set to the default placeholder."""
    if not key or not key.strip():
        return True
    return key.strip().lower() in ("your-key-here", "your-openrouter-key-here", "placeholder")


def check_api_key_configuration() -> bool:
    """Explicitly check and warn if OpenRouter API key is missing or placeholder."""
    key = settings.openrouter_api_key or os.getenv("OPENROUTER_API_KEY", "")
    if is_placeholder_key(key):
        logger.warning(
            "\n"
            "====================================================================\n"
            "⚠️  WARNING: OPENROUTER_API_KEY is not configured or is a placeholder!\n"
            "   Discovery will run in FALLBACK MODE (is_fallback: true).\n"
            "   To enable live LLM scouting, provide a valid OpenRouter API key.\n"
            "====================================================================\n"
        )
        return False
    return True


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


def _call_openrouter_api(
    api_key: str,
    model: str,
    user_prompt: str,
    timeout: float = 35.0,
) -> tuple[bool, str]:
    """Call OpenRouter chat completions endpoint with structured json_object format."""
    headers = {
        "Authorization": f"Bearer {api_key.strip()}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SCOUT_SCORING_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.2,
    }

    with httpx.Client(timeout=timeout) as client:
        res = client.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=headers,
            json=payload,
        )
        if res.status_code != 200:
            logger.warning(
                "OpenRouter model %s returned status %d: %s",
                model,
                res.status_code,
                res.text[:200],
            )
            return False, ""
        data = res.json()
        choices = data.get("choices") or []
        if not choices:
            logger.warning("OpenRouter model %s returned no choices: %s", model, str(data)[:200])
            return False, ""
        content = choices[0].get("message", {}).get("content", "")
        return True, content


def execute_scout_and_score(
    strategy_name: str,
    strategy_config: dict[str, Any],
    items: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], str, str]:
    """
    Executes Scout + Scoring combined.
    Returns: (scored_ideas, raw_prompt, raw_llm_response)
    
    Fallback chain:
    1. Primary model: nvidia/nemotron-3-super-120b-a12b:free
    2. Fallback model: openrouter/free
    3. If neither available or key is placeholder: Rule-based fallback evaluator
       with explicit "is_fallback": true in scoring_metadata and loud warning.
    """
    user_prompt = build_scout_prompt(strategy_name, strategy_config, items)
    api_key = settings.openrouter_api_key or os.getenv("OPENROUTER_API_KEY", "")

    is_key_valid = not is_placeholder_key(api_key)
    raw_response = ""
    used_model = None
    is_fallback = False

    if is_key_valid:
        # Step 1: Try Primary Model
        logger.info("Calling OpenRouter with Primary Model: %s", PRIMARY_MODEL)
        try:
            success, content = _call_openrouter_api(api_key, PRIMARY_MODEL, user_prompt)
            if success and content.strip():
                raw_response = content
                used_model = PRIMARY_MODEL
        except Exception as e:
            logger.warning("Primary model %s failed: %s", PRIMARY_MODEL, str(e))

        # Step 2: Try Fallback Model if primary failed
        if not raw_response:
            logger.info("Falling back to OpenRouter auto-router: %s", FALLBACK_MODEL)
            try:
                success, content = _call_openrouter_api(api_key, FALLBACK_MODEL, user_prompt)
                if success and content.strip():
                    raw_response = content
                    used_model = FALLBACK_MODEL
            except Exception as e:
                logger.warning("Fallback model %s failed: %s", FALLBACK_MODEL, str(e))

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

    # Clean potential markdown fences from response
    cleaned = raw_response.strip()
    if cleaned.startswith("```json"):
        cleaned = cleaned[len("```json"):].strip()
    if cleaned.startswith("```"):
        cleaned = cleaned[len("```"):].strip()
    if cleaned.endswith("```"):
        cleaned = cleaned[:-len("```")].strip()

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
