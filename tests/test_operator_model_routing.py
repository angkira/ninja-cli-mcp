"""Operator ↔ model auto-routing tests.

The model selected for a task must always be runnable by the active operator:
an OpenRouter id must never be handed to Codex, and each operator falls back to
its own default when the configured model belongs to a different operator.
"""

from __future__ import annotations

import os

import pytest

from ninja_coder.driver import NinjaConfig
from ninja_coder.model_selector import ModelSelector
from ninja_coder.models import TaskComplexity
from ninja_common.defaults import DEFAULT_CODER_MODEL
from ninja_common.operator_models import (
    is_model_compatible,
    operator_default_model,
    operator_from_bin,
    resolve_operator_model,
)


OPENROUTER_ID = "openrouter/deepseek/deepseek-v4.1-flash"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("codex", "codex"),
        ("/usr/local/bin/codex", "codex"),
        ("/home/u/.nvm/versions/node/v25.0.0/bin/codex", "codex"),
        ("/opt/aider/bin/aider", "aider"),
        ("opencode", "opencode"),
        ("gemini", "gemini"),
        ("claude", "claude"),
        ("junie", "junie"),
        ("unknown-cli", None),
        ("", None),
    ],
)
def test_operator_from_bin(raw: str, expected: str | None) -> None:
    assert operator_from_bin(raw) == expected


def test_native_operator_rejects_foreign_model() -> None:
    assert is_model_compatible(OPENROUTER_ID, "codex") is False
    assert is_model_compatible(operator_default_model("codex") or "", "codex") is True


def test_aider_requires_provider_prefixed_model() -> None:
    assert is_model_compatible("openrouter/anthropic/claude-sonnet-4", "aider") is True
    assert is_model_compatible("gpt-5.6-luna", "aider") is False


def test_opencode_accepts_any_model() -> None:
    assert is_model_compatible("anything/goes", "opencode") is True


def test_resolve_operator_model_swaps_incompatible() -> None:
    assert resolve_operator_model(OPENROUTER_ID, "codex") == operator_default_model("codex")
    assert resolve_operator_model(OPENROUTER_ID, "opencode") == OPENROUTER_ID
    assert resolve_operator_model("gpt-5.6-luna", "aider") == operator_default_model("aider")


@pytest.mark.parametrize("complexity", list(TaskComplexity))
def test_selector_never_returns_foreign_model_for_codex(complexity: TaskComplexity) -> None:
    selector = ModelSelector(default_model=OPENROUTER_ID, operator="codex")
    assert selector.select_model(complexity).model == operator_default_model("codex")


def test_selector_class_override_enforced_for_codex(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NINJA_MODEL_CLASS_SMART", OPENROUTER_ID)
    selector = ModelSelector(default_model=OPENROUTER_ID, operator="codex")
    assert selector.select_by_class("smart").model == operator_default_model("codex")


def test_selector_keeps_compatible_explicit_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NINJA_MODEL_QUICK", "gpt-5.4")
    selector = ModelSelector(default_model=OPENROUTER_ID, operator="codex")
    assert selector.select_model(TaskComplexity.QUICK).model == "gpt-5.4"


def test_selector_opencode_keeps_openrouter_default() -> None:
    selector = ModelSelector(default_model=OPENROUTER_ID, operator="opencode")
    assert selector.select_model(TaskComplexity.QUICK).model == OPENROUTER_ID


def test_from_env_codex_defaults_to_codex_model(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in (
        "NINJA_MODEL",
        "NINJA_CODER_MODEL",
        "OPENROUTER_MODEL",
        "OPENAI_MODEL",
        "NINJA_MODEL_CLASS_SMART",
    ):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("NINJA_CODE_BIN", "codex")
    config = NinjaConfig.from_env()
    assert config.model == operator_default_model("codex")


def test_from_env_opencode_keeps_coder_default(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in ("NINJA_MODEL", "NINJA_CODER_MODEL", "OPENROUTER_MODEL", "OPENAI_MODEL"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("NINJA_CODE_BIN", "opencode")
    config = NinjaConfig.from_env()
    assert config.model == os.environ.get("NINJA_MODEL", DEFAULT_CODER_MODEL)


def test_from_env_explicit_model_wins(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NINJA_CODE_BIN", "codex")
    monkeypatch.setenv("NINJA_AGENT_MODEL", "gpt-5.4")
    config = NinjaConfig.from_env(model_env="NINJA_AGENT_MODEL")
    assert config.model == "gpt-5.4"
