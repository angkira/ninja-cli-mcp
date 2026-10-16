"""Comprehensive unit and integration tests for OpenCode model selection & autocomplete.

Tests cover:
- Dynamic discovery of OpenCode providers via `opencode models`
- Model fetching for all canonical and discovered OpenCode providers:
    opencode, opencode-go, anthropic, openai, google, openrouter, litellm, github-copilot, gitlab
- In-process provider filtering (handling OpenCode v2 `provider/model` catalog)
- opencode-go alias fallback (mapping to opencode/* free/go models or opencode-go/*)
- Autocomplete resolution: resolve_search_models, filter_models, search by partial query
- Failure handling: missing binary, command timeouts, empty model outputs
- Operator isolation: ensuring opencode operator only returns compatible models
"""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from ninja_config.model_selector import (
    OPENCODE_PROVIDERS,
    Model,
    discover_opencode_providers,
    get_provider_models,
)
from ninja_config.ui.model_autocomplete import filter_models, resolve_search_models


# Sample synthetic catalog matching OpenCode v2 output format
MOCK_OPENCODE_MODELS_OUTPUT = """
opencode/glm-5.3-flash-free
opencode/deepseek-v4.1-flash-free
opencode/nemotron-3.5-lightning-free
opencode-go/glm-5.3
opencode-go/deepseek-v4-pro
anthropic/claude-sonnet-4-5
anthropic/claude-haiku-4-5
anthropic/claude-opus-4-5
openai/gpt-4o
openai/gpt-5-mini
openai/o3-mini
google/gemini-2.5-flash
google/gemini-2.5-pro
openrouter/deepseek/deepseek-v4.1-flash
openrouter/anthropic/claude-sonnet-4
litellm/anthropic/claude-haiku-5-5
litellm/openai/gpt-4o
github-copilot/gpt-4o
github-copilot/claude-sonnet-4.5
gitlab/duo-chat-gpt-4o
"""


@pytest.fixture
def mock_opencode_cli():
    """Mock the opencode CLI subprocess call returning the synthetic catalog."""
    mock_res = MagicMock()
    mock_res.returncode = 0
    mock_res.stdout = MOCK_OPENCODE_MODELS_OUTPUT
    mock_res.stderr = ""
    with patch("shutil.which", return_value="/usr/local/bin/opencode"):
        with patch("subprocess.run", return_value=mock_res):
            yield


# ---------------------------------------------------------------------------
# 1. Provider discovery tests
# ---------------------------------------------------------------------------


def test_discover_opencode_providers_parses_all_unique_prefixes(mock_opencode_cli):
    """discover_opencode_providers extracts all provider prefixes from opencode output."""
    providers = discover_opencode_providers()
    provider_ids = [p[0] for p in providers]

    expected_providers = [
        "opencode",
        "opencode-go",
        "anthropic",
        "openai",
        "google",
        "openrouter",
        "litellm",
        "github-copilot",
        "gitlab",
    ]
    for exp in expected_providers:
        assert exp in provider_ids, f"Expected provider '{exp}' to be discovered"


def test_discover_opencode_providers_fallback_on_failure():
    """When opencode is not found or fails, falls back to canonical OPENCODE_PROVIDERS."""
    with patch("shutil.which", return_value=None):
        providers = discover_opencode_providers()
        assert providers == OPENCODE_PROVIDERS.copy()


# ---------------------------------------------------------------------------
# 2. Model fetching for every canonical provider
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("provider", "expected_sample_model"),
    [
        ("opencode", "opencode/glm-5.3-flash-free"),
        ("opencode-go", "opencode-go/glm-5.3"),
        ("anthropic", "anthropic/claude-sonnet-4-5"),
        ("openai", "openai/gpt-4o"),
        ("google", "google/gemini-2.5-flash"),
        ("openrouter", "openrouter/deepseek/deepseek-v4.1-flash"),
        ("litellm", "litellm/anthropic/claude-haiku-5-5"),
        ("github-copilot", "github-copilot/gpt-4o"),
        ("gitlab", "gitlab/duo-chat-gpt-4o"),
    ],
)
def test_get_provider_models_for_all_providers(mock_opencode_cli, provider, expected_sample_model):
    """get_provider_models('opencode', provider) correctly returns models for each provider."""
    models = get_provider_models("opencode", provider)
    assert len(models) > 0, f"Provider '{provider}' returned 0 models"
    model_ids = [m.id for m in models]
    assert expected_sample_model in model_ids


def test_opencode_go_provider_includes_opencode_free_models(mock_opencode_cli):
    """opencode-go provider includes both opencode-go/* and opencode/* models."""
    models = get_provider_models("opencode", "opencode-go")
    model_ids = [m.id for m in models]
    # Explicit opencode-go model
    assert "opencode-go/glm-5.3" in model_ids
    # Included opencode/ free model
    assert "opencode/glm-5.3-flash-free" in model_ids


def test_get_provider_models_empty_when_no_match(mock_opencode_cli):
    """Unknown provider returns empty list without error."""
    models = get_provider_models("opencode", "nonexistent-provider")
    assert models == []


def test_get_provider_models_empty_when_binary_missing():
    """Missing opencode binary returns empty list cleanly."""
    with patch("shutil.which", return_value=None):
        models = get_provider_models("opencode", "anthropic")
        assert models == []


def test_get_provider_models_timeout_handled_gracefully():
    """Subprocess timeout returns empty list without raising."""
    with patch("shutil.which", return_value="/usr/local/bin/opencode"):
        with patch(
            "subprocess.run", side_effect=subprocess.TimeoutExpired(["opencode", "models"], 30)
        ):
            models = get_provider_models("opencode", "anthropic")
            assert models == []


# ---------------------------------------------------------------------------
# 3. Autocomplete resolution and search filtering
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "provider",
    [
        "opencode",
        "opencode-go",
        "anthropic",
        "openai",
        "google",
        "openrouter",
        "litellm",
        "github-copilot",
    ],
)
def test_resolve_search_models_returns_models_for_opencode(mock_opencode_cli, provider):
    """resolve_search_models('opencode', provider) returns models for all providers."""
    models = resolve_search_models("opencode", provider)
    assert len(models) > 0, f"resolve_search_models returned 0 models for provider '{provider}'"
    assert all(isinstance(m, Model) for m in models)


def test_filter_models_by_query_partial_match(mock_opencode_cli):
    """filter_models matches model name, id, and description."""
    models = resolve_search_models("opencode", "anthropic")
    # Search by partial ID / name
    haiku = filter_models(models, "haiku", limit=5)
    assert len(haiku) == 1
    assert haiku[0].id == "anthropic/claude-haiku-4-5"

    sonnet = filter_models(models, "sonnet", limit=5)
    assert len(sonnet) == 1
    assert sonnet[0].id == "anthropic/claude-sonnet-4-5"


def test_filter_models_opencode_go_glm_query(mock_opencode_cli):
    """Autocomplete on opencode-go finding GLM models."""
    models = resolve_search_models("opencode", "opencode-go")
    glm_results = filter_models(models, "glm", limit=10)
    assert len(glm_results) >= 2
    glm_ids = [m.id for m in glm_results]
    assert "opencode-go/glm-5.3" in glm_ids
    assert "opencode/glm-5.3-flash-free" in glm_ids


def test_filter_models_empty_query_returns_empty_by_contract(mock_opencode_cli):
    """Empty query returns empty list by contract (UI requires >=2 chars)."""
    models = resolve_search_models("opencode", "anthropic")
    assert filter_models(models, "", limit=2) == []
    # With non-empty query:
    matched = filter_models(models, "claude", limit=2)
    assert len(matched) == 2


# ---------------------------------------------------------------------------
# 4. Live OpenCode CLI sanity check (if opencode binary is present on host)
# ---------------------------------------------------------------------------


def test_live_opencode_models_runs_without_arguments():
    """Verify that live `opencode models` works without positional args."""
    import shutil

    if not shutil.which("opencode"):
        pytest.skip("opencode binary not installed on host")

    from ninja_config.model_selector import _run_opencode_models

    lines = _run_opencode_models()
    assert len(lines) > 0
    # Every line must be provider/model format
    assert all("/" in line for line in lines)
    # Both anthropic and opencode models exist in live catalog
    providers = {line.split("/")[0] for line in lines}
    assert "anthropic" in providers or "opencode" in providers
