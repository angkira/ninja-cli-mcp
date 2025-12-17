"""
Integration tests for OpenRouter API connection.

These tests verify the connection to OpenRouter and model availability.
"""

import os

import pytest
import httpx


# Skip these tests if not in integration test mode
pytestmark = pytest.mark.skipif(
    not os.environ.get("RUN_INTEGRATION_TESTS"),
    reason="Integration tests only run when RUN_INTEGRATION_TESTS=1",
)


def test_openrouter_api_key_format():
    """Test that API key is properly formatted."""
    api_key = os.environ.get("OPENROUTER_API_KEY") or os.environ.get("OPENAI_API_KEY")

    if not api_key:
        pytest.skip("No API key configured")

    # Check API key doesn't contain ANSI codes
    assert "\x1b" not in api_key, "API key contains ANSI escape codes"
    assert "[" not in api_key or api_key.startswith("sk-or-v1-"), "API key might contain terminal formatting"

    # Check reasonable length
    assert len(api_key) > 20, f"API key too short: {len(api_key)} chars"
    assert len(api_key) < 100, f"API key too long: {len(api_key)} chars (might contain escape codes)"

    # Check starts with expected prefix
    assert api_key.startswith("sk-"), f"API key doesn't start with 'sk-'"


@pytest.mark.slow
def test_openrouter_api_connection():
    """Test basic connection to OpenRouter API."""
    api_key = os.environ.get("OPENROUTER_API_KEY") or os.environ.get("OPENAI_API_KEY")

    if not api_key:
        pytest.skip("No API key configured")

    # Test the /api/v1/models endpoint
    try:
        response = httpx.get(
            "https://openrouter.ai/api/v1/models",
            headers={
                "Authorization": f"Bearer {api_key}",
                "HTTP-Referer": "https://github.com/angkira/ninja-cli-mcp",
                "X-Title": "ninja-cli-mcp integration test",
            },
            timeout=10.0,
        )

        # Should get 200 OK or 401 Unauthorized (if key is invalid)
        assert response.status_code in [200, 401], f"Unexpected status: {response.status_code}"

        if response.status_code == 200:
            data = response.json()
            assert "data" in data, "Response missing 'data' field"
            assert len(data["data"]) > 0, "No models returned"

            # Check that some expected models are available
            model_ids = [model["id"] for model in data["data"]]

            # At least one Claude model should be available
            claude_models = [m for m in model_ids if "claude" in m.lower()]
            assert len(claude_models) > 0, "No Claude models found"

            # At least one OpenAI model should be available
            openai_models = [m for m in model_ids if "gpt" in m.lower() or "openai" in m.lower()]
            assert len(openai_models) > 0, "No OpenAI models found"
        elif response.status_code == 401:
            pytest.fail(f"API key authentication failed: {response.text}")

    except httpx.ConnectError as e:
        pytest.fail(f"Failed to connect to OpenRouter: {e}")
    except httpx.TimeoutException:
        pytest.skip("OpenRouter API timed out (network issue)")


@pytest.mark.slow
def test_openrouter_chat_completion_minimal():
    """Test minimal chat completion to verify authentication works."""
    api_key = os.environ.get("OPENROUTER_API_KEY") or os.environ.get("OPENAI_API_KEY")

    if not api_key:
        pytest.skip("No API key configured")

    # Use the cheapest model for testing
    test_model = "anthropic/claude-haiku-4.5-20250929"

    try:
        response = httpx.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "HTTP-Referer": "https://github.com/angkira/ninja-cli-mcp",
                "X-Title": "ninja-cli-mcp integration test",
                "Content-Type": "application/json",
            },
            json={
                "model": test_model,
                "messages": [
                    {"role": "user", "content": "Say 'OK'"}
                ],
                "max_tokens": 10,
            },
            timeout=30.0,
        )

        assert response.status_code in [200, 400, 401, 402], f"Unexpected status: {response.status_code}"

        if response.status_code == 200:
            data = response.json()
            assert "choices" in data, "Response missing 'choices' field"
            assert len(data["choices"]) > 0, "No choices returned"
            assert "message" in data["choices"][0], "Choice missing 'message' field"

            # Check that we got a response
            message = data["choices"][0]["message"]
            assert "content" in message, "Message missing 'content' field"
            assert len(message["content"]) > 0, "Empty response content"

        elif response.status_code == 401:
            pytest.fail(f"API key authentication failed: {response.text}")
        elif response.status_code == 402:
            pytest.skip("Insufficient credits for API call")
        elif response.status_code == 400:
            # Check if it's a model availability issue
            error_data = response.json()
            if "error" in error_data:
                error_msg = str(error_data["error"])
                if "model" in error_msg.lower():
                    pytest.skip(f"Model not available: {test_model}")
            pytest.fail(f"Bad request: {response.text}")

    except httpx.ConnectError as e:
        pytest.fail(f"Failed to connect to OpenRouter: {e}")
    except httpx.TimeoutException:
        pytest.skip("OpenRouter API timed out (network issue)")


def test_openrouter_config_from_env():
    """Test that configuration is properly loaded from environment."""
    from ninja_cli_mcp.ninja_driver import NinjaConfig

    # Save original env vars
    original_key = os.environ.get("OPENROUTER_API_KEY")
    original_model = os.environ.get("NINJA_MODEL")

    try:
        # Set test values
        os.environ["OPENROUTER_API_KEY"] = "sk-test-key"
        os.environ["NINJA_MODEL"] = "anthropic/claude-sonnet-4"

        config = NinjaConfig.from_env()

        assert config.openai_api_key == "sk-test-key"
        assert config.model == "anthropic/claude-sonnet-4"
        assert config.openai_base_url == "https://openrouter.ai/api/v1"

    finally:
        # Restore original env vars
        if original_key:
            os.environ["OPENROUTER_API_KEY"] = original_key
        else:
            os.environ.pop("OPENROUTER_API_KEY", None)

        if original_model:
            os.environ["NINJA_MODEL"] = original_model
        else:
            os.environ.pop("NINJA_MODEL", None)
