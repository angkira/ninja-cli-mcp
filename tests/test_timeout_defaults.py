"""Tests for timeout defaults and env overrides (2026-07 timeout tuning).

Covers:
- OpenCodeStrategy.get_timeout per-type defaults and env overrides
- driver._get_inactivity_timeout per-type defaults and env override
- tools plan-timeout estimates (sequential/parallel)
"""

from __future__ import annotations

from unittest.mock import Mock

import pytest

from ninja_coder.driver import NinjaConfig, _get_inactivity_timeout
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
    """Per-type inactivity defaults: quick=60s, sequential/parallel=120s."""
    monkeypatch.delenv("NINJA_INACTIVITY_TIMEOUT", raising=False)

    assert _get_inactivity_timeout("quick") == 60.0
    assert _get_inactivity_timeout("sequential") == 120.0
    assert _get_inactivity_timeout("parallel") == 120.0
    # Plan variants inherit their base type's default
    assert _get_inactivity_timeout("sequential_plan") == 120.0
    assert _get_inactivity_timeout("parallel_plan") == 120.0
    # Unknown types fall back to the quick default
    assert _get_inactivity_timeout("something-else") == 60.0


def test_inactivity_timeout_env_overrides_all_types(monkeypatch):
    """NINJA_INACTIVITY_TIMEOUT, when set, overrides every task type."""
    monkeypatch.setenv("NINJA_INACTIVITY_TIMEOUT", "20")

    for task_type in ("quick", "sequential", "parallel", "sequential_plan"):
        assert _get_inactivity_timeout(task_type) == 20.0


def _make_steps(count: int) -> list[PlanStep]:
    return [PlanStep(id=f"s{i}", title=f"Step {i}", task=f"Do {i}") for i in range(count)]


def test_estimate_sequential_timeout():
    """Sequential estimate: 600 + 120 * steps."""
    executor = ToolExecutor(driver=Mock())
    request = SequentialPlanRequest(repo_root="/tmp/test", steps=_make_steps(3))
    assert executor._estimate_sequential_timeout(request) == 600 + 120 * 3


def test_estimate_parallel_timeout():
    """Parallel estimate: 600 + 60 * max(1, steps // fanout)."""
    executor = ToolExecutor(driver=Mock())
    request = ParallelPlanRequest(repo_root="/tmp/test", fanout=2, steps=_make_steps(4))
    assert executor._estimate_parallel_timeout(request) == 600 + 60 * 2

    # Fewer steps than fanout still charges one wave
    request = ParallelPlanRequest(repo_root="/tmp/test", fanout=4, steps=_make_steps(2))
    assert executor._estimate_parallel_timeout(request) == 600 + 60 * 1
