#!/usr/bin/env python3
"""
Unit and Integration Tests for OpenRouter Failure Classification and Fallback.
Tests:
1. 401/403 Authentication Error (non-retryable, halts immediately).
2. 429 Rate Limit Error (transient, parses Retry-After header).
3. 500/503/Timeout Error (transient, retryable).
4. 400 Bad Request Error (non-retryable request error).
5. Malformed JSON / Empty choices response (transient error).
6. Primary model failure with successful secondary fallback.
7. Complete fallback chain failure (all models fail).
8. Verify no fake research content is returned on failure.
"""
from unittest.mock import MagicMock, patch
import httpx

from app.llm.openrouter_client import (
    call_openrouter_api,
    execute_llm_completion,
    OpenRouterAuthError,
    OpenRouterRateLimitError,
    OpenRouterTransientError,
    OpenRouterRequestError,
)
from app.workflows.research_provider import execute_research_for_idea
from app.ideas.models import Idea, IdeaStatus
from app.strategies.models import ContentStrategy
from app.db import SessionLocal
from uuid import uuid4


def test_401_auth_error():
    with patch("httpx.Client.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_resp.text = "Unauthorized: Invalid API key"
        mock_post.return_value = mock_resp

        try:
            call_openrouter_api(
                api_key="sk-or-v1-fakekey",
                model="test-model",
                system_prompt="sys",
                user_prompt="usr",
            )
            assert False, "Should have raised OpenRouterAuthError"
        except OpenRouterAuthError as e:
            assert "401" in str(e)
            print("✓ Test 1: 401 correctly classified as OpenRouterAuthError")


def test_429_rate_limit_error():
    with patch("httpx.Client.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 429
        mock_resp.headers = {"Retry-After": "30"}
        mock_resp.text = "Rate limit exceeded"
        mock_post.return_value = mock_resp

        try:
            call_openrouter_api(
                api_key="sk-or-v1-fakekey",
                model="test-model",
                system_prompt="sys",
                user_prompt="usr",
            )
            assert False, "Should have raised OpenRouterRateLimitError"
        except OpenRouterRateLimitError as e:
            assert e.retry_after == 30.0
            print("✓ Test 2: 429 correctly classified as OpenRouterRateLimitError with retry_after=30")


def test_500_503_transient_error():
    with patch("httpx.Client.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 503
        mock_resp.text = "Service Unavailable"
        mock_post.return_value = mock_resp

        try:
            call_openrouter_api(
                api_key="sk-or-v1-fakekey",
                model="test-model",
                system_prompt="sys",
                user_prompt="usr",
            )
            assert False, "Should have raised OpenRouterTransientError"
        except OpenRouterTransientError as e:
            assert "503" in str(e)
            print("✓ Test 3: 503 correctly classified as OpenRouterTransientError")


def test_400_bad_request_error():
    with patch("httpx.Client.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 400
        mock_resp.text = "Bad Request: Invalid model parameters"
        mock_post.return_value = mock_resp

        try:
            call_openrouter_api(
                api_key="sk-or-v1-fakekey",
                model="test-model",
                system_prompt="sys",
                user_prompt="usr",
            )
            assert False, "Should have raised OpenRouterRequestError"
        except OpenRouterRequestError as e:
            assert "400" in str(e)
            print("✓ Test 4: 400 correctly classified as OpenRouterRequestError")


def test_malformed_response_error():
    with patch("httpx.Client.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"choices": []}  # empty choices
        mock_post.return_value = mock_resp

        try:
            call_openrouter_api(
                api_key="sk-or-v1-fakekey",
                model="test-model",
                system_prompt="sys",
                user_prompt="usr",
            )
            assert False, "Should have raised OpenRouterTransientError"
        except OpenRouterTransientError as e:
            assert "no choices" in str(e)
            print("✓ Test 5: Empty choices correctly classified as OpenRouterTransientError")


def test_successful_fallback():
    # Primary fails with 500, Secondary succeeds with valid JSON
    with patch("app.llm.openrouter_client.call_openrouter_api") as mock_call:
        def side_effect(api_key, model, **kwargs):
            if "nemotron" in model:
                raise OpenRouterTransientError("500 upstream timeout")
            return '{"response": "success from secondary"}'

        mock_call.side_effect = side_effect

        with patch("app.llm.openrouter_client.settings") as mock_settings:
            mock_settings.openrouter_api_key = "sk-valid-test-key"
            success, content, used_model, is_fallback = execute_llm_completion(
                system_prompt="sys",
                user_prompt="usr",
            )
            assert success is True
            assert is_fallback is True
            assert "gemma" in used_model
            assert "success from secondary" in content
            print(f"✓ Test 6: Primary failure successfully fell back to {used_model}")


def test_all_models_fail():
    with patch("app.llm.openrouter_client.call_openrouter_api") as mock_call:
        mock_call.side_effect = OpenRouterTransientError("503 Service Unavailable")

        with patch("app.llm.openrouter_client.settings") as mock_settings:
            mock_settings.openrouter_api_key = "sk-valid-test-key"
            try:
                execute_llm_completion(
                    system_prompt="sys",
                    user_prompt="usr",
                )
                assert False, "Should have raised OpenRouterTransientError when all models fail"
            except OpenRouterTransientError as e:
                assert "All models in fallback chain failed" in str(e)
                print("✓ Test 7: All models failed correctly raised informative OpenRouterTransientError")


def test_no_fake_research_content_on_failure():
    # Verify execute_research_for_idea does NOT generate fake research content when OpenRouter fails
    from tests.test_publishing_concurrency import get_raw_pg_conn
    conn = get_raw_pg_conn()
    cur = conn.cursor()
    strat_id = uuid4()
    idea_id = uuid4()
    try:
        cur.execute(
            "INSERT INTO content_strategies (id, name, description, config, enabled) VALUES (%s, %s, %s, %s, true)",
            (strat_id, "Test Strat", "Testing", "{}"),
        )
        cur.execute(
            "INSERT INTO ideas (id, strategy_id, title, status, scoring_metadata) VALUES (%s, %s, %s, %s, %s)",
            (idea_id, strat_id, "Integrity Verification Test", "SELECTED", "{}"),
        )
        conn.commit()

        db = SessionLocal()
        try:
            with patch("app.workflows.research_provider.execute_llm_completion") as mock_llm:
                mock_llm.side_effect = OpenRouterTransientError("All models failed")
                try:
                    execute_research_for_idea(db, idea_id)
                    assert False, "Research provider must not return fake content on failure"
                except OpenRouterTransientError:
                    print("✓ Test 8: execute_research_for_idea strictly propagates error and produces no fake content")
        finally:
            db.close()
    finally:
        cur.execute("DELETE FROM ideas WHERE id = %s", (idea_id,))
        cur.execute("DELETE FROM content_strategies WHERE id = %s", (strat_id,))
        conn.commit()
        cur.close()
        conn.close()


if __name__ == "__main__":
    print("=" * 60)
    print("RUNNING OPENROUTER ERROR CLASSIFICATION TEST SUITE")
    print("=" * 60)
    test_401_auth_error()
    test_429_rate_limit_error()
    test_500_503_transient_error()
    test_400_bad_request_error()
    test_malformed_response_error()
    test_successful_fallback()
    test_all_models_fail()
    test_no_fake_research_content_on_failure()
    print("\n" + "=" * 60)
    print("ALL OPENROUTER FAILURE TESTS PASSED!")
    print("=" * 60)
