"""Tests for model fallback on quota/rate-limit/overload errors.

No network access: the driver is fully mocked. Covers:
- ``NINJA_FALLBACK_MODELS`` chain parsing (empty/dupes/whitespace)
- Simple task: 429 on attempt 1 -> retry uses the fallback model id
- Exhausted chain -> the last error surfaces unchanged
- Non-model error (auth) -> no fallback consumed
- Sequential plan path honors the fallback chain
"""

from __future__ import annotations

import copy
import json
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, Mock

import pytest

from ninja_coder.driver import NinjaConfig, NinjaDriver, NinjaResult
from ninja_coder.models import ExecutionMode, PlanStep, SequentialPlanRequest, SimpleTaskRequest
from ninja_coder.tools import (
    ToolExecutor,
    is_model_side_error,
    parse_fallback_chain,
)


if TYPE_CHECKING:
    from pathlib import Path


PRIMARY = "openrouter/primary-model"
FALLBACK_A = "openrouter/deepseek/deepseek-v4.1-flash"
FALLBACK_B = "openrouter/google/gemini-3-flash"


def _rate_limit_result() -> NinjaResult:
    """A retryable model-side failure (HTTP 429)."""
    return NinjaResult(
        success=False,
        summary="❌ OpenCode failed: 429 rate limit exceeded for primary model",
        notes="rate limit exceeded, please retry after a moment",
        suspected_touched_paths=[],
        raw_logs_path="",
        exit_code=1,
        stdout="",
        stderr="ERROR 429: rate limit exceeded",
        model_used=PRIMARY,
        aider_error_detected=True,
    )


def _recorded_side_effect(mock_driver: Mock, results: list[NinjaResult]) -> list[dict[str, object]]:
    """Queue driver results while deep-copying each attempt's instruction.

    The executor mutates the instruction dict in place when swapping in a
    fallback model, so the mock's recorded call args would otherwise all show
    the final state. Snapshots isolate each attempt's actual model pinning.
    """
    seen: list[dict[str, object]] = []
    queue = list(results)

    async def _fake_execute(*args: object, **kwargs: object) -> NinjaResult:
        seen.append(copy.deepcopy(kwargs["instruction"]))  # type: ignore[arg-type]
        return queue.pop(0)

    mock_driver.execute_async.side_effect = _fake_execute
    return seen


def _auth_result() -> NinjaResult:
    """A non-model failure (auth) that must never trigger fallback."""
    return NinjaResult(
        success=False,
        summary="❌ Authentication error",
        notes="❌ Authentication failed. Check OPENROUTER_API_KEY in ~/.ninja-mcp.env",
        suspected_touched_paths=[],
        raw_logs_path="",
        exit_code=1,
        stdout="",
        stderr="Unauthorized: invalid api key",
        model_used=PRIMARY,
        aider_error_detected=False,
    )


def _success_result() -> NinjaResult:
    return NinjaResult(
        success=True,
        summary="✅ Task completed successfully",
        notes="done",
        suspected_touched_paths=[],
        raw_logs_path="",
        exit_code=0,
        stdout="ok",
        stderr="",
        model_used=FALLBACK_A,
        aider_error_detected=False,
    )


@pytest.fixture
def mock_driver() -> Mock:
    driver = Mock(spec=NinjaDriver)
    driver.config = NinjaConfig(model=PRIMARY, bin_path="opencode")
    driver._strategy = Mock()
    driver._strategy.name = "opencode"
    driver.session_manager = Mock()
    driver.structured_logger = Mock()
    driver.execute_async = AsyncMock()
    return driver


@pytest.fixture
def executor(mock_driver: Mock) -> ToolExecutor:
    return ToolExecutor(driver=mock_driver)


@pytest.fixture
def temp_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "test_repo"
    repo.mkdir()
    (repo / "src").mkdir()
    (repo / "src" / "__init__.py").write_text("")
    return repo


class TestParseFallbackChain:
    def test_empty_unset_returns_no_fallback(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("NINJA_FALLBACK_MODELS", raising=False)
        assert parse_fallback_chain(PRIMARY) == []

    def test_empty_string_returns_no_fallback(self) -> None:
        assert parse_fallback_chain(PRIMARY, raw="") == []
        assert parse_fallback_chain(PRIMARY, raw="  , , ") == []

    def test_whitespace_stripped(self) -> None:
        chain = parse_fallback_chain(PRIMARY, raw=f"  {FALLBACK_A} , {FALLBACK_B}  ")
        assert chain == [FALLBACK_A, FALLBACK_B]

    def test_dupes_of_primary_dropped(self) -> None:
        chain = parse_fallback_chain(
            PRIMARY, raw=f"{PRIMARY},{FALLBACK_A}, {PRIMARY} ,{FALLBACK_A}"
        )
        assert chain == [FALLBACK_A]

    def test_example_from_spec(self) -> None:
        chain = parse_fallback_chain(
            "openrouter/some-primary",
            raw="openrouter/deepseek/deepseek-v4.1-flash,openrouter/google/gemini-3-flash",
        )
        assert chain == [
            "openrouter/deepseek/deepseek-v4.1-flash",
            "openrouter/google/gemini-3-flash",
        ]


class TestIsModelSideError:
    @pytest.mark.parametrize(
        "text",
        [
            "ERROR 429: rate limit exceeded",
            "HTTP 503 Service Unavailable",
            "quota-exhausted for model",
            "model overloaded, try again later",
            "Rate limit hit on provider",
            "insufficient quota for this model",
            "Model overloaded (server busy)",
        ],
    )
    def test_model_side_signatures_match(self, text: str) -> None:
        result = NinjaResult(
            success=False,
            summary=text,
            notes="",
            model_used=PRIMARY,
            aider_error_detected=True,
        )
        assert is_model_side_error(result) is True

    @pytest.mark.parametrize(
        "text",
        [
            "❌ Authentication failed. Check OPENROUTER_API_KEY",
            "Unauthorized: invalid api key",
            "💰 Insufficient credits. Add credits at openrouter.ai",
            "Model 'foo/bar' not found on OpenRouter",
            "Safety check failed",
        ],
    )
    def test_non_model_signatures_do_not_match(self, text: str) -> None:
        result = NinjaResult(
            success=False,
            summary=text,
            notes="",
            model_used=PRIMARY,
            aider_error_detected=False,
        )
        assert is_model_side_error(result) is False


class TestSimpleTaskFallback:
    async def test_429_then_success_uses_fallback_id(
        self,
        executor: ToolExecutor,
        mock_driver: Mock,
        temp_repo: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Attempt 1 fails with 429 -> attempt 2 runs with the fallback model."""
        monkeypatch.setenv("NINJA_FALLBACK_MODELS", f"{FALLBACK_A},{FALLBACK_B}")
        monkeypatch.setenv("NINJA_RETRY_DELAY_SEC", "0")
        seen = _recorded_side_effect(mock_driver, [_rate_limit_result(), _success_result()])

        request = SimpleTaskRequest(task="Add a helper", repo_root=str(temp_repo))
        result = await executor.simple_task(request)

        assert result.status == "ok"
        assert mock_driver.execute_async.call_count == 2
        assert "model_override" not in seen[0]
        assert seen[1]["model_override"] == FALLBACK_A

    async def test_exhausted_chain_surfaces_last_error(
        self,
        executor: ToolExecutor,
        mock_driver: Mock,
        temp_repo: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """All models fail -> the LAST error is returned unchanged."""
        monkeypatch.setenv("NINJA_FALLBACK_MODELS", FALLBACK_A)
        monkeypatch.setenv("NINJA_RETRY_DELAY_SEC", "0")
        monkeypatch.setenv("NINJA_MAX_RETRIES", "1")
        last = _rate_limit_result()
        last.notes = "rate limit exceeded on fallback model (LAST)"
        seen = _recorded_side_effect(mock_driver, [_rate_limit_result(), last])

        request = SimpleTaskRequest(task="Add a helper", repo_root=str(temp_repo))
        result = await executor.simple_task(request)

        assert result.status == "error"
        assert mock_driver.execute_async.call_count == 2
        assert seen[1]["model_override"] == FALLBACK_A
        assert "LAST" in result.notes

    async def test_auth_error_consumes_no_fallback(
        self,
        executor: ToolExecutor,
        mock_driver: Mock,
        temp_repo: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Non-model error -> single attempt, no model_override set."""
        monkeypatch.setenv("NINJA_FALLBACK_MODELS", f"{FALLBACK_A},{FALLBACK_B}")
        monkeypatch.setenv("NINJA_RETRY_DELAY_SEC", "0")
        mock_driver.execute_async.side_effect = [_auth_result()]

        request = SimpleTaskRequest(task="Add a helper", repo_root=str(temp_repo))
        result = await executor.simple_task(request)

        assert result.status == "error"
        assert mock_driver.execute_async.call_count == 1
        instruction = mock_driver.execute_async.call_args_list[0].kwargs["instruction"]
        assert "model_override" not in instruction

    async def test_no_fallback_chain_preserves_behavior(
        self,
        executor: ToolExecutor,
        mock_driver: Mock,
        temp_repo: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Unset NINJA_FALLBACK_MODELS -> retry same model, no override."""
        monkeypatch.delenv("NINJA_FALLBACK_MODELS", raising=False)
        monkeypatch.setenv("NINJA_RETRY_DELAY_SEC", "0")
        monkeypatch.setenv("NINJA_MAX_RETRIES", "1")
        mock_driver.execute_async.side_effect = [_rate_limit_result(), _success_result()]

        request = SimpleTaskRequest(task="Add a helper", repo_root=str(temp_repo))
        result = await executor.simple_task(request)

        assert result.status == "ok"
        assert mock_driver.execute_async.call_count == 2
        for call in mock_driver.execute_async.call_args_list:
            assert "model_override" not in call.kwargs["instruction"]


class TestSequentialPlanFallback:
    def _plan_request(self, temp_repo: Path) -> SequentialPlanRequest:
        return SequentialPlanRequest(
            repo_root=str(temp_repo),
            mode=ExecutionMode.QUICK,
            steps=[
                PlanStep(
                    id="step1",
                    title="Create thing",
                    task="Create a thing",
                    context_paths=[],
                ),
            ],
        )

    def _plan_success(self) -> NinjaResult:
        stdout = json.dumps(
            {
                "overall_status": "success",
                "steps_completed": ["step1"],
                "steps_failed": [],
                "step_summaries": {"step1": "Created thing"},
                "files_modified": [],
            }
        )
        return NinjaResult(
            success=True,
            summary="✅ Task completed successfully",
            notes="",
            suspected_touched_paths=[],
            raw_logs_path="",
            exit_code=0,
            stdout=f"```json\n{stdout}\n```",
            stderr="",
            model_used=FALLBACK_A,
            aider_error_detected=False,
        )

    async def test_sequential_plan_falls_back_on_429(
        self,
        executor: ToolExecutor,
        mock_driver: Mock,
        temp_repo: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("NINJA_FALLBACK_MODELS", FALLBACK_A)
        seen = _recorded_side_effect(mock_driver, [_rate_limit_result(), self._plan_success()])

        result = await executor.execute_plan_sequential(self._plan_request(temp_repo))

        assert result.overall_status == "success"
        assert mock_driver.execute_async.call_count == 2
        assert seen[1]["model_override"] == FALLBACK_A
