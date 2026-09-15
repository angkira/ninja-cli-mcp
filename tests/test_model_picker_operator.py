"""The model picker must follow the selected operator.

For a native operator (codex/junie/claude/gemini) only its own provider is
valid, so a stored model id from a different operator must not leak its prefix
into the picker. Aider is OpenRouter-backed.
"""

from __future__ import annotations

import pytest

from ninja_config.ui.model_autocomplete import ModelRolePicker


class _StubConfig:
    def __init__(self, data: dict[str, str]) -> None:
        self._data = data

    def get(self, key: str, default: object = None) -> object:
        return self._data.get(key, default)


def _picker(operator: str, model: str) -> ModelRolePicker:
    cfg = _StubConfig({"NINJA_CODE_BIN": operator, "NINJA_MODEL_QUICK": model})
    return ModelRolePicker(
        role="quick",
        env_var="NINJA_MODEL_QUICK",
        default="opencode/glm-4.7-free",
        config=cfg,  # type: ignore[arg-type]
    )


@pytest.mark.parametrize(
    ("operator", "model", "expected_provider"),
    [
        ("codex", "openrouter/deepseek/deepseek-v4.1-flash", "codex"),
        ("claude", "claude-sonnet-4", "anthropic"),
        ("gemini", "gemini-3-flash", "google"),
        ("junie", "deepseek-v4-flash", "junie"),
        ("aider", "openrouter/anthropic/claude-sonnet-4", "openrouter"),
        ("opencode", "openrouter/deepseek/deepseek-v4.1-flash", "openrouter"),
    ],
)
def test_picker_provider_follows_operator(
    operator: str, model: str, expected_provider: str
) -> None:
    assert _picker(operator, model)._provider == expected_provider


def test_native_operator_offers_only_its_provider() -> None:
    """A stale OpenRouter model under codex shows only the codex provider."""
    picker = _picker("codex", "openrouter/deepseek/deepseek-v4.1-flash")

    values = [value for _, value in picker._initial_options()]

    assert values == ["codex"]
