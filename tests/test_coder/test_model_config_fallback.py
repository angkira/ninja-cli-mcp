"""Task-specific model resolution must fall back to the persisted config.

``~/.ninja-mcp.env`` is exported into ``os.environ`` by every MCP server entry
point, but direct-driver and test paths never load it. ``ModelSelector`` must
therefore consult the persisted config itself when a ``NINJA_MODEL_*``
environment variable is absent, while keeping env precedence unchanged.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest

import ninja_common.config_manager as config_manager_module
from ninja_coder.model_selector import ModelSelector
from ninja_coder.models import TaskComplexity


if TYPE_CHECKING:
    from pytest import MonkeyPatch


QUICK_MODEL = "opencode-go/test-quick"
SEQUENTIAL_MODEL = "opencode-go/test-sequential"
PARALLEL_MODEL = "zai-coding-plan/test-parallel"

CONFIG_CONTENT = f"""\
# Test configuration
NINJA_MODEL=openrouter/deepseek/deepseek-v4.1-flash
NINJA_MODEL_QUICK={QUICK_MODEL}
NINJA_MODEL_SEQUENTIAL={SEQUENTIAL_MODEL}
NINJA_MODEL_PARALLEL={PARALLEL_MODEL}
export NINJA_MODEL_CLASS_SMART='opencode-go/test-smart'
"""


@pytest.fixture(autouse=True)
def _clear_task_model_env(monkeypatch: MonkeyPatch) -> None:
    """Remove task-specific / model-class env overrides for determinism."""
    for key in (
        "NINJA_MODEL",
        "NINJA_MODEL_QUICK",
        "NINJA_MODEL_SEQUENTIAL",
        "NINJA_MODEL_PARALLEL",
        "NINJA_MODEL_CLASS_SMART",
        "NINJA_MODEL_CLASS_BALANCED",
        "NINJA_MODEL_CLASS_FAST",
    ):
        monkeypatch.delenv(key, raising=False)


def _point_config_at(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
    content: str | None,
) -> list[Path]:
    """Redirect ``ConfigManager()`` at a temp config file.

    Args:
        monkeypatch: Pytest monkeypatch fixture.
        tmp_path: Directory for the temp config file.
        content: File contents, or ``None`` to leave the file absent.

    Returns:
        List that grows on every ``read_config`` call (read counter).
    """
    config_file = tmp_path / "ninja-mcp.env"
    if content is not None:
        config_file.write_text(content)

    reads: list[Path] = []
    real_manager = config_manager_module.ConfigManager

    class CountingConfigManager(real_manager):  # type: ignore[misc, valid-type]
        """ConfigManager pinned to the temp file, counting read_config calls."""

        def __init__(self, config_file_path: str | None = None) -> None:
            super().__init__(config_file=str(config_file))

        def read_config(self) -> dict[str, str]:
            reads.append(self.config_file)
            return super().read_config()

    monkeypatch.setattr(config_manager_module, "ConfigManager", CountingConfigManager)
    return reads


def test_config_file_used_when_env_absent(monkeypatch: MonkeyPatch, tmp_path: Path) -> None:
    """With no env override, the persisted config supplies the quick model."""
    _point_config_at(monkeypatch, tmp_path, CONFIG_CONTENT)

    selector = ModelSelector(default_model="bad/ambient", operator="opencode")
    recommendation = selector.select_model(TaskComplexity.QUICK)

    assert recommendation.model == QUICK_MODEL
    assert "task-specific" in recommendation.reason
    assert "quick" in recommendation.reason


def test_env_override_beats_config_file(monkeypatch: MonkeyPatch, tmp_path: Path) -> None:
    """An explicit env var still wins over the persisted config."""
    _point_config_at(monkeypatch, tmp_path, CONFIG_CONTENT)
    monkeypatch.setenv("NINJA_MODEL_QUICK", "opencode-go/env-quick")

    selector = ModelSelector(default_model="bad/ambient", operator="opencode")
    recommendation = selector.select_model(TaskComplexity.QUICK)

    assert recommendation.model == "opencode-go/env-quick"


def test_missing_config_falls_back_to_default(monkeypatch: MonkeyPatch, tmp_path: Path) -> None:
    """Without a config file the previous behaviour is preserved."""
    _point_config_at(monkeypatch, tmp_path, None)

    selector = ModelSelector(default_model="bad/ambient", operator="opencode")
    recommendation = selector.select_model(TaskComplexity.QUICK)

    assert recommendation.model == "bad/ambient"
    assert recommendation.reason == "User-configured default model"


def test_config_read_once_per_selection(monkeypatch: MonkeyPatch, tmp_path: Path) -> None:
    """The config file is read at most once per ``select_model`` call."""
    reads = _point_config_at(monkeypatch, tmp_path, CONFIG_CONTENT)

    selector = ModelSelector(default_model="bad/ambient", operator="opencode")
    selector.select_model(TaskComplexity.QUICK)

    assert len(reads) == 1


def test_ambient_default_does_not_win_over_config(monkeypatch: MonkeyPatch, tmp_path: Path) -> None:
    """Regression: an ambient ``NINJA_MODEL`` must not hijack task routing."""
    _point_config_at(monkeypatch, tmp_path, CONFIG_CONTENT)
    monkeypatch.setenv("NINJA_MODEL", "qwen/nonexistent")

    selector = ModelSelector(default_model="qwen/nonexistent", operator="opencode")

    assert selector.select_model(TaskComplexity.QUICK).model == QUICK_MODEL
    assert selector.select_model(TaskComplexity.SEQUENTIAL).model == SEQUENTIAL_MODEL
    assert selector.select_model(TaskComplexity.PARALLEL).model == PARALLEL_MODEL
