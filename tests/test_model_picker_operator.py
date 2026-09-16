"""The model picker must follow the selected operator.

For a native operator (codex/junie/claude/agy) only its own provider is
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
        ("agy", "gemini-3.8-flash-medium", "agy"),
        ("junie", "deepseek-v4-flash", "junie"),
        ("junie", "gemini-3.8-flash", "junie"),
        ("junie", "grok-4.6", "junie"),
        ("junie", "gpt-5.6-luna", "junie"),
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


def test_opencode_has_no_hardcoded_model_fallback() -> None:
    """OpenCode models are discovered dynamically — never a static list."""
    from ninja_config.ui.model_autocomplete import static_models_for_provider

    assert static_models_for_provider("anthropic", "opencode") == []
    assert static_models_for_provider("openrouter", "opencode") == []


def test_opencode_provider_dropdown_starts_without_hardcoded_list() -> None:
    """Before discovery the picker shows only the current provider (hidden)."""
    picker = _picker("opencode", "openrouter/deepseek/deepseek-v4.1-flash")

    options = picker._initial_options()

    assert options == [("OpenRouter", "openrouter")]


def test_single_provider_operators_hide_dropdown() -> None:
    """Native/aider operators expose exactly one provider (dropdown hidden)."""
    assert len(_picker("codex", "gpt-5.6-luna")._initial_options()) == 1
    assert len(_picker("aider", "openrouter/anthropic/claude-sonnet-4")._initial_options()) == 1


@pytest.mark.parametrize(
    "model",
    ["deepseek-v4-flash", "gemini-3.8-flash", "grok-4.6", "gpt-5.6-luna"],
)
def test_guess_provider_keeps_junie_ids_on_junie(model: str) -> None:
    """Junie flat ids (incl. gpt-5.6-luna) must not be misclassified as openai."""
    from ninja_config.ui.model_autocomplete import guess_provider

    assert guess_provider(model, operator="junie") == "junie"


def test_junie_static_models_cover_versioned_ids() -> None:
    """The picker fallback offers the verified versioned Junie ids."""
    from ninja_config.ui.model_autocomplete import static_models_for_provider

    ids = {m.id for m in static_models_for_provider("junie", "junie")}
    assert {"deepseek-v4-flash", "gemini-3.8-flash", "grok-4.6", "gpt-5.6-luna"} <= ids
