"""Tests for timeout defaults and env overrides (2026-07 timeout tuning).

Covers:
- OpenCodeStrategy.get_timeout per-type defaults and env overrides
- driver._get_inactivity_timeout per-type defaults and env override
- tools plan-timeout estimates (sequential/parallel)
"""

from __future__ import annotations

from unittest.mock import Mock

import pytest

from ninja_coder.driver import NinjaConfig, _get_absolute_timeout, _get_inactivity_timeout
from ninja_coder.models import ParallelPlanRequest, PlanStep, SequentialPlanRequest
from ninja_coder.strategies.opencode_strategy import OpenCodeStrategy
from ninja_coder.tools import ToolExecutor


_TIMEOUT_ENV_VARS = [
    "NINJA_OPENCODE_QUICK_TIMEOUT",
    "NINJA_OPENCODE_SEQUENTIAL_TIMEOUT",
    "NINJA_OPENCODE_PARALLEL_TIMEOUT",
    "NINJA_OPENCODE_TIMEOUT",
]


@pytest.fixture
def strategy(monkeypatch):
    """OpenCode strategy with all timeout env vars cleared."""
    for var in _TIMEOUT_ENV_VARS:
        monkeypatch.delenv(var, raising=False)
    config = NinjaConfig(bin_path="opencode", model="test/model", openai_api_key="test")
    return OpenCodeStrategy("opencode", config)


def test_opencode_get_timeout_defaults(strategy):
    """New per-type defaults: quick=600, sequential=900, parallel=1200, fallback=600."""
    assert strategy.get_timeout("quick") == 600
    assert strategy.get_timeout("sequential") == 900
    assert strategy.get_timeout("parallel") == 1200
    assert strategy.get_timeout("sequential_plan") == 900
    assert strategy.get_timeout("unknown-type") == 600


def test_opencode_get_timeout_env_overrides(strategy, monkeypatch):
    """Each task type is individually configurable via env var."""
    monkeypatch.setenv("NINJA_OPENCODE_QUICK_TIMEOUT", "700")
    monkeypatch.setenv("NINJA_OPENCODE_SEQUENTIAL_TIMEOUT", "1000")
    monkeypatch.setenv("NINJA_OPENCODE_PARALLEL_TIMEOUT", "1500")

    assert strategy.get_timeout("quick") == 700
    assert strategy.get_timeout("sequential") == 1000
    assert strategy.get_timeout("parallel") == 1500

    # Fallback for unknown task types uses NINJA_OPENCODE_TIMEOUT
    monkeypatch.setenv("NINJA_OPENCODE_TIMEOUT", "450")
    assert strategy.get_timeout("unknown-type") == 450


def test_inactivity_timeout_defaults(monkeypatch):
    """Per-type inactivity defaults: quick=90s, sequential/parallel=180s."""
    monkeypatch.delenv("NINJA_INACTIVITY_TIMEOUT", raising=False)

    assert _get_inactivity_timeout("quick") == 90.0
    assert _get_inactivity_timeout("sequential") == 180.0
    assert _get_inactivity_timeout("parallel") == 180.0
    # Plan variants inherit their base type's default
    assert _get_inactivity_timeout("sequential_plan") == 180.0
    assert _get_inactivity_timeout("parallel_plan") == 180.0
    # Unknown types fall back to the quick default
    assert _get_inactivity_timeout("something-else") == 90.0


def test_inactivity_timeout_env_overrides_all_types(monkeypatch):
    """NINJA_INACTIVITY_TIMEOUT, when set, overrides every task type."""
    monkeypatch.setenv("NINJA_INACTIVITY_TIMEOUT", "20")

    for task_type in ("quick", "sequential", "parallel", "sequential_plan"):
        assert _get_inactivity_timeout(task_type) == 20.0


def test_absolute_timeout_zero_disables_deadline(monkeypatch):
    """An explicit zero disables the hard wall-clock deadline."""
    for var in (
        "NINJA_ABSOLUTE_TIMEOUT_SEC",
        "NINJA_ABSOLUTE_TIMEOUT_QUICK",
        "NINJA_ABSOLUTE_TIMEOUT_SEQUENTIAL",
        "NINJA_ABSOLUTE_TIMEOUT_PARALLEL",
        "NINJA_TIMEOUT_SEC",
    ):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("NINJA_ABSOLUTE_TIMEOUT_SEC", "0")
    assert _get_absolute_timeout("quick") is None


def test_absolute_timeout_per_type_defaults_and_overrides(monkeypatch):
    """Absolute deadlines resolve by task type and support overrides."""
    monkeypatch.delenv("NINJA_TIMEOUT_SEC", raising=False)
    monkeypatch.delenv("NINJA_ABSOLUTE_TIMEOUT_SEC", raising=False)
    monkeypatch.delenv("NINJA_ABSOLUTE_TIMEOUT_QUICK", raising=False)
    assert _get_absolute_timeout("quick") == 1800.0
    assert _get_absolute_timeout("sequential_plan") == 7200.0
    monkeypatch.setenv("NINJA_ABSOLUTE_TIMEOUT_SEQUENTIAL", "123")
    assert _get_absolute_timeout("sequential_plan") == 123.0


def _make_steps(count: int) -> list[PlanStep]:
    return [PlanStep(id=f"s{i}", title=f"Step {i}", task=f"Do {i}") for i in range(count)]


def test_estimate_sequential_timeout():
    """Sequential plans defer the absolute deadline to the driver."""
    executor = ToolExecutor(driver=Mock())
    request = SequentialPlanRequest(repo_root="/tmp/test", steps=_make_steps(3))
    assert executor._estimate_sequential_timeout(request) is None


def test_estimate_parallel_timeout():
    """Parallel plans defer the absolute deadline to the driver."""
    executor = ToolExecutor(driver=Mock())
    request = ParallelPlanRequest(repo_root="/tmp/test", fanout=2, steps=_make_steps(4))
    assert executor._estimate_parallel_timeout(request) is None

    # Fewer steps than fanout also has no tool-level wall-clock estimate.
    request = ParallelPlanRequest(repo_root="/tmp/test", fanout=4, steps=_make_steps(2))
    assert executor._estimate_parallel_timeout(request) is None
