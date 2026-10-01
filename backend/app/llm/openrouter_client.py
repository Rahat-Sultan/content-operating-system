import json
import logging
import os
from typing import Any
import httpx

from app.config import settings

logger = logging.getLogger(__name__)

PRIMARY_MODEL = "nvidia/nemotron-3-super-120b-a12b:free"
SECONDARY_MODEL = "google/gemma-4-26b-a4b-it:free"
FALLBACK_MODEL = "openrouter/free"


def is_placeholder_key(key: str | None) -> bool:
    """Check if the API key is missing, empty, or set to the default placeholder."""
    if not key or not key.strip():
        return True
    return key.strip().lower() in ("your-key-here", "your-openrouter-key-here", "placeholder")


def check_api_key_configuration(operation_name: str = "LLM Generation") -> bool:
    """Explicitly check and warn loudly if OpenRouter API key is missing or placeholder."""
    key = settings.openrouter_api_key or os.getenv("OPENROUTER_API_KEY", "")
    if is_placeholder_key(key):
        logger.warning(
            "\n"
            "====================================================================\n"
            f"⚠️  WARNING: OPENROUTER_API_KEY is not configured or is a placeholder!\n"
            f"   {operation_name} will run in FALLBACK MODE (is_fallback: true).\n"
            "   To enable live LLM generation, provide a valid OpenRouter API key.\n"
            "====================================================================\n"
        )
        return False
    return True


def call_openrouter_api(
    api_key: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
    response_format: dict[str, str] | None = None,
    temperature: float = 0.2,
    timeout: float = 40.0,
) -> tuple[bool, str]:
    """
    Call OpenRouter chat completions endpoint.
    Returns (success, response_content_string).
    """
    headers = {
        "Authorization": f"Bearer {api_key.strip()}",
        "Content-Type": "application/json",
    }
    payload: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": temperature,
    }
    if response_format:
        payload["response_format"] = response_format

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


def execute_llm_completion(
    system_prompt: str,
    user_prompt: str,
    operation_name: str = "LLM Generation",
    response_format: dict[str, str] | None = None,
    temperature: float = 0.2,
) -> tuple[bool, str, str | None, bool]:
    """
    Standard OpenRouter calling chain with Primary -> Fallback -> Failure.
    Returns: (success, raw_content, used_model, is_fallback)
    
    If the key is invalid or all models fail:
    returns (False, "", None, True)
    """
    api_key = settings.openrouter_api_key or os.getenv("OPENROUTER_API_KEY", "")
    is_valid_key = not is_placeholder_key(api_key)

    if not is_valid_key:
        check_api_key_configuration(operation_name)
        return False, "", None, True

    # 1. Try Primary Model
    logger.info("[%s] Calling OpenRouter Primary Model: %s", operation_name, PRIMARY_MODEL)
    try:
        success, content = call_openrouter_api(
            api_key=api_key,
            model=PRIMARY_MODEL,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response_format=response_format,
            temperature=temperature,
            timeout=15.0,
        )
        if success and content.strip():
            return True, content, PRIMARY_MODEL, False
    except Exception as e:
        logger.warning("[%s] Primary model %s failed: %s", operation_name, PRIMARY_MODEL, e)

    # 2. Try Secondary Model
    logger.info("[%s] Calling OpenRouter Secondary Model: %s", operation_name, SECONDARY_MODEL)
    try:
        success, content = call_openrouter_api(
            api_key=api_key,
            model=SECONDARY_MODEL,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response_format=response_format,
            temperature=temperature,
            timeout=15.0,
        )
        if success and content.strip():
            return True, content, SECONDARY_MODEL, False
    except Exception as e:
        logger.warning("[%s] Secondary model %s failed: %s", operation_name, SECONDARY_MODEL, e)

    # 3. Try Fallback Model
    logger.info("[%s] Falling back to OpenRouter model: %s", operation_name, FALLBACK_MODEL)
    try:
        success, content = call_openrouter_api(
            api_key=api_key,
            model=FALLBACK_MODEL,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response_format=response_format,
            temperature=temperature,
            timeout=15.0,
        )
        if success and content.strip():
            return True, content, FALLBACK_MODEL, False
    except Exception as e:
        logger.warning("[%s] Fallback model %s failed: %s", operation_name, FALLBACK_MODEL, e)

    # Both failed
    check_api_key_configuration(operation_name)
    return False, "", None, True


def clean_json_markdown(text: str) -> str:
    """Strips markdown code fences if LLM wrapped JSON in ```json ... ```."""
    cleaned = text.strip()
    if cleaned.startswith("```json"):
        cleaned = cleaned[len("```json"):].strip()
    if cleaned.startswith("```"):
        cleaned = cleaned[len("```"):].strip()
    if cleaned.endswith("```"):
        cleaned = cleaned[:-len("```")].strip()
    return cleaned
