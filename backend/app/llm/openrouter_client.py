import json
import logging
import os
from typing import Any
import httpx

from app.config import settings
from app.accounts.context import active_key

logger = logging.getLogger(__name__)

PRIMARY_MODEL = "nvidia/nemotron-3-super-120b-a12b:free"
SECONDARY_MODEL = "google/gemma-4-26b-a4b-it:free"
FALLBACK_MODEL = "openrouter/free"


class OpenRouterError(Exception):
    """Base exception for OpenRouter operations."""
    pass


class OpenRouterAuthError(OpenRouterError):
    """401/403 or missing/placeholder API key. Non-retryable."""
    pass


class OpenRouterRateLimitError(OpenRouterError):
    """429 Rate limit encountered. Transient, respect Retry-After if present."""
    def __init__(self, message: str, retry_after: float | None = None):
        super().__init__(message)
        self.retry_after = retry_after


class OpenRouterTransientError(OpenRouterError):
    """500, 502, 503, 504, 408, network timeouts, DNS resolution failure. Retryable."""
    pass


class OpenRouterRequestError(OpenRouterError):
    """400 Bad Request, 404 Model Not Found, malformed payload. Non-retryable."""
    pass


def is_placeholder_key(key: str | None) -> bool:
    """Check if the API key is missing, empty, or set to the default placeholder."""
    if not key or not key.strip():
        return True
    return key.strip().lower() in ("your-key-here", "your-openrouter-key-here", "placeholder")


def check_api_key_configuration(operation_name: str = "LLM Generation") -> bool:
    """Explicitly check and warn loudly if OpenRouter API key is missing or placeholder."""
    key = active_key("OPENROUTER_API_KEY") or ""
    if is_placeholder_key(key):
        logger.warning(
            "\n"
            "====================================================================\n"
            f"⚠️  WARNING: OPENROUTER_API_KEY is not configured or is a placeholder!\n"
            f"   {operation_name} will fail or require fallback.\n"
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
    timeout: float = 25.0,
) -> str:
    """
    Call OpenRouter chat completions endpoint with classified exceptions.
    Returns response content string on success, or raises classified OpenRouterError.
    """
    if is_placeholder_key(api_key):
        raise OpenRouterAuthError("OpenRouter API key is missing, empty, or placeholder.")

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

    try:
        with httpx.Client(timeout=timeout) as client:
            res = client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers=headers,
                json=payload,
            )
    except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout, httpx.WriteTimeout, httpx.NetworkError) as net_err:
        err_type = type(net_err).__name__
        logger.warning("OpenRouter network failure for model %s: %s: %s", model, err_type, net_err)
        raise OpenRouterTransientError(f"Network failure calling OpenRouter ({err_type}): {net_err}") from net_err

    status_code = res.status_code
    if status_code == 200:
        try:
            data = res.json()
        except Exception as json_err:
            raise OpenRouterTransientError(f"Malformed JSON response from OpenRouter: {json_err}") from json_err

        choices = data.get("choices") or []
        if not choices:
            raise OpenRouterTransientError(f"OpenRouter model {model} returned 200 OK with no choices in payload")
        content = choices[0].get("message", {}).get("content", "")
        if not content:
            raise OpenRouterTransientError(f"OpenRouter model {model} returned 200 OK with empty content")
        return content

    # Error classification based on HTTP status
    err_body = res.text[:300].strip()
    if status_code in (401, 403):
        raise OpenRouterAuthError(f"OpenRouter authentication failed (HTTP {status_code}) for model {model}: {err_body}")

    if status_code == 429:
        retry_after_hdr = res.headers.get("Retry-After")
        retry_after_val: float | None = None
        if retry_after_hdr:
            try:
                retry_after_val = float(retry_after_hdr)
            except ValueError:
                pass
        raise OpenRouterRateLimitError(
            f"OpenRouter rate limit reached (HTTP 429) for model {model}: {err_body}",
            retry_after=retry_after_val,
        )

    if status_code in (408, 500, 502, 503, 504):
        raise OpenRouterTransientError(
            f"OpenRouter upstream service error (HTTP {status_code}) for model {model}: {err_body}"
        )

    if status_code in (400, 404, 422):
        raise OpenRouterRequestError(
            f"OpenRouter request error (HTTP {status_code}) for model {model}: {err_body}"
        )

    raise OpenRouterError(f"OpenRouter unexpected HTTP {status_code} for model {model}: {err_body}")


def execute_llm_completion(
    system_prompt: str,
    user_prompt: str,
    operation_name: str = "LLM Generation",
    response_format: dict[str, str] | None = None,
    temperature: float = 0.2,
) -> tuple[bool, str, str | None, bool]:
    """
    Standard OpenRouter calling chain with Primary -> Secondary -> Fallback.
    Returns: (success, raw_content, used_model, is_fallback)

    If all models fail or key is invalid:
    Raises the most informative classified OpenRouterError describing all attempted models and failures.
    """
    api_key = active_key("OPENROUTER_API_KEY") or ""
    if is_placeholder_key(api_key):
        check_api_key_configuration(operation_name)
        raise OpenRouterAuthError(
            f"[{operation_name}] OPENROUTER_API_KEY is not configured or is a placeholder. Live LLM generation cannot run."
        )

    models_chain = [
        ("primary", PRIMARY_MODEL),
        ("secondary", SECONDARY_MODEL),
        ("fallback", FALLBACK_MODEL),
    ]

    attempt_errors: list[str] = []

    for stage, model in models_chain:
        logger.info("[%s] Attempting %s model: %s", operation_name, stage, model)
        try:
            content = call_openrouter_api(
                api_key=api_key,
                model=model,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                response_format=response_format,
                temperature=temperature,
                timeout=25.0,
            )
            is_fallback = (stage != "primary")
            logger.info("[%s] Succeeded using %s model: %s", operation_name, stage, model)
            return True, content, model, is_fallback
        except OpenRouterAuthError as auth_err:
            # Auth errors are not model-specific, halt immediately without trying other models
            logger.error("[%s] Non-retryable auth error on model %s: %s", operation_name, model, auth_err)
            raise
        except OpenRouterRequestError as req_err:
            logger.warning("[%s] Non-retryable request error on model %s: %s", operation_name, model, req_err)
            attempt_errors.append(f"{model} (HTTP Request Error: {req_err})")
            # Proceed to next model in fallback chain
        except OpenRouterRateLimitError as rate_err:
            logger.warning("[%s] Rate limit on model %s: %s", operation_name, model, rate_err)
            attempt_errors.append(f"{model} (Rate Limit 429: {rate_err})")
        except OpenRouterTransientError as trans_err:
            logger.warning("[%s] Transient error on model %s: %s", operation_name, model, trans_err)
            attempt_errors.append(f"{model} (Transient/Network: {trans_err})")
        except Exception as unk_err:
            logger.warning("[%s] Unexpected error on model %s: %s", operation_name, model, unk_err)
            attempt_errors.append(f"{model} ({type(unk_err).__name__}: {unk_err})")

    # All models failed in the chain
    summary_msg = f"[{operation_name}] All models in fallback chain failed: " + "; ".join(attempt_errors)
    logger.error(summary_msg)
    raise OpenRouterTransientError(summary_msg)


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
