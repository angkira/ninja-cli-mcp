"""Tests for Ninja Code CLI driver."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ninja_cli_mcp.models import ExecutionMode, PlanStep, TestPlan
from ninja_cli_mcp.ninja_driver import (
    DEFAULT_MODEL,
    RECOMMENDED_MODELS,
    InstructionBuilder,
    NinjaConfig,
    NinjaDriver,
    NinjaResult,
)


class TestNinjaConfig:
    """Tests for NinjaConfig."""

    def test_default_values(self) -> None:
        config = NinjaConfig()
        assert config.bin_path == "ninja-code"
        assert config.openai_base_url == "https://openrouter.ai/api/v1"
        assert config.model == DEFAULT_MODEL
        assert config.timeout_sec == 600

    def test_from_env(self, mock_env: dict[str, str]) -> None:
        config = NinjaConfig.from_env()
        assert config.openai_api_key == mock_env["OPENROUTER_API_KEY"]
        assert config.model == mock_env["NINJA_MODEL"]
        assert config.bin_path == mock_env["NINJA_CODE_BIN"]

    def test_from_env_fallback_to_openai_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        monkeypatch.delenv("NINJA_MODEL", raising=False)
        monkeypatch.setenv("OPENAI_API_KEY", "openai-key-123")

        config = NinjaConfig.from_env()
        assert config.openai_api_key == "openai-key-123"

    def test_with_model(self) -> None:
        config = NinjaConfig(model="anthropic/claude-sonnet-4")
        new_config = config.with_model("openai/gpt-4o")

        assert new_config.model == "openai/gpt-4o"
        assert config.model == "anthropic/claude-sonnet-4"  # Original unchanged

    def test_recommended_models_exist(self) -> None:
        assert len(RECOMMENDED_MODELS) > 0
        assert "anthropic/claude-sonnet-4" in RECOMMENDED_MODELS
        assert "openai/gpt-4o" in RECOMMENDED_MODELS
        assert "qwen/qwen3-coder" in RECOMMENDED_MODELS


class TestInstructionBuilder:
    """Tests for InstructionBuilder."""

    def test_build_quick_task(self, temp_repo: Path) -> None:
        builder = InstructionBuilder(str(temp_repo), ExecutionMode.QUICK)
        instruction = builder.build_quick_task(
            task="Add a hello function",
            context_paths=["src/"],
            allowed_globs=["**/*.py"],
            deny_globs=["**/__pycache__/**"],
        )

        assert instruction["version"] == "1.0"
        assert instruction["type"] == "quick_task"
        assert instruction["repo_root"] == str(temp_repo)
        assert instruction["task"] == "Add a hello function"
        assert instruction["mode"] == "quick"
        assert instruction["file_scope"]["context_paths"] == ["src/"]
        assert instruction["file_scope"]["allowed_globs"] == ["**/*.py"]
        assert instruction["file_scope"]["deny_globs"] == ["**/__pycache__/**"]
        assert "instructions" in instruction
        assert "guarantees" in instruction

    def test_build_quick_task_default_globs(self, temp_repo: Path) -> None:
        builder = InstructionBuilder(str(temp_repo))
        instruction = builder.build_quick_task(
            task="Do something",
            context_paths=[],
            allowed_globs=[],
            deny_globs=[],
        )

        # Should default to allow all
        assert instruction["file_scope"]["allowed_globs"] == ["**/*"]
        assert instruction["file_scope"]["deny_globs"] == []

    def test_build_plan_step_quick_mode(self, temp_repo: Path) -> None:
        builder = InstructionBuilder(str(temp_repo), ExecutionMode.QUICK)
        step = PlanStep(
            id="step-001",
            title="Add feature",
            task="Implement the feature",
            context_paths=["src/"],
            allowed_globs=["src/**/*.py"],
        )

        instruction = builder.build_plan_step(
            step=step,
            global_allowed_globs=["**/*.md"],
            global_deny_globs=["**/venv/**"],
        )

        assert instruction["type"] == "plan_step"
        assert instruction["step"]["id"] == "step-001"
        assert instruction["step"]["title"] == "Add feature"
        assert instruction["mode"] == "quick"
        assert "Single coder pass" in instruction["instructions"]

    def test_build_plan_step_full_mode(self, temp_repo: Path) -> None:
        builder = InstructionBuilder(str(temp_repo), ExecutionMode.FULL)
        step = PlanStep(
            id="step-001",
            title="Add feature",
            task="Implement the feature",
            max_iterations=5,
            test_plan=TestPlan(unit=["pytest tests/"], e2e=["npm run e2e"]),
        )

        instruction = builder.build_plan_step(
            step=step,
            global_allowed_globs=[],
            global_deny_globs=[],
        )

        assert instruction["mode"] == "full"
        assert "Full pipeline" in instruction["instructions"]
        assert "5 fix iterations" in instruction["instructions"]
        assert "pytest tests/" in instruction["instructions"]

    def test_build_plan_step_merges_globs(self, temp_repo: Path) -> None:
        builder = InstructionBuilder(str(temp_repo))
        step = PlanStep(
            id="1",
            title="Test",
            task="Task",
            allowed_globs=["src/**"],
            deny_globs=["**/*.pyc"],
        )

        instruction = builder.build_plan_step(
            step=step,
            global_allowed_globs=["**/*.py"],
            global_deny_globs=["**/venv/**"],
        )

        # Should have both step and global globs
        allowed = instruction["file_scope"]["allowed_globs"]
        denied = instruction["file_scope"]["deny_globs"]

        assert "src/**" in allowed
        assert "**/*.py" in allowed
        assert "**/*.pyc" in denied
        assert "**/venv/**" in denied

    def test_build_test_task(self, temp_repo: Path) -> None:
        builder = InstructionBuilder(str(temp_repo))
        instruction = builder.build_test_task(
            commands=["pytest tests/", "npm test"],
            timeout_sec=300,
        )

        assert instruction["type"] == "test_task"
        assert instruction["test_commands"] == ["pytest tests/", "npm test"]
        assert instruction["timeout_sec"] == 300
        assert "pytest tests/" in instruction["instructions"]
        assert "npm test" in instruction["instructions"]

    def test_guarantees_structure(self, temp_repo: Path) -> None:
        builder = InstructionBuilder(str(temp_repo))
        instruction = builder.build_quick_task("task", [], [], [])

        guarantees = instruction["guarantees"]
        assert "file_access" in guarantees
        assert "orchestrator_role" in guarantees
        assert "scope_enforcement" in guarantees
        assert "test_execution" in guarantees


class TestNinjaDriver:
    """Tests for NinjaDriver."""

    def test_initialization(self) -> None:
        config = NinjaConfig(bin_path="test-bin")
        driver = NinjaDriver(config)
        assert driver.config.bin_path == "test-bin"

    def test_initialization_from_env(self, mock_env: dict[str, str]) -> None:
        driver = NinjaDriver()
        assert driver.config.openai_api_key == mock_env["OPENROUTER_API_KEY"]

    def test_get_env(self, mock_env: dict[str, str]) -> None:
        config = NinjaConfig(
            openai_base_url="https://test.api/v1",
            openai_api_key="test-key",
            model="test-model",
        )
        driver = NinjaDriver(config)

        env = driver._get_env()
        assert env["OPENAI_BASE_URL"] == "https://test.api/v1"
        assert env["OPENAI_API_KEY"] == "test-key"
        assert env["OPENAI_MODEL"] == "test-model"

    def test_write_task_file(self, temp_repo: Path) -> None:
        driver = NinjaDriver()
        instruction = {"task": "test", "data": "value"}

        task_file = driver._write_task_file(
            str(temp_repo),
            "test-step",
            instruction,
        )

        assert task_file.exists()
        assert task_file.suffix == ".json"
        assert "test-step" in task_file.name

        with open(task_file) as f:
            data = json.load(f)
        assert data["task"] == "test"

    def test_parse_output_success(self) -> None:
        driver = NinjaDriver()
        result = driver._parse_output(
            stdout="Task completed successfully\nModified src/main.py",
            stderr="",
            exit_code=0,
        )

        assert result.success is True
        assert result.exit_code == 0
        assert "src/main.py" in result.suspected_touched_paths

    def test_parse_output_failure(self) -> None:
        driver = NinjaDriver()
        result = driver._parse_output(
            stdout="Starting task...",
            stderr="Error: file not found",
            exit_code=1,
        )

        assert result.success is False
        assert result.exit_code == 1
        assert "Error: file not found" in result.notes

    def test_parse_output_with_json_summary(self) -> None:
        driver = NinjaDriver()
        stdout = """Processing...
{"summary": "Added 2 functions", "notes": "Minor changes"}
Done."""

        result = driver._parse_output(stdout, "", 0)
        assert result.summary == "Added 2 functions"
        assert result.notes == "Minor changes"

    def test_parse_output_extracts_file_paths(self) -> None:
        driver = NinjaDriver()
        stdout = """Modified file: src/utils.py
Created src/new_file.py
Wrote 'tests/test_new.py'
Editing config.json"""

        result = driver._parse_output(stdout, "", 0)
        paths = result.suspected_touched_paths

        assert "src/utils.py" in paths
        assert "src/new_file.py" in paths

    def test_execute_sync_file_not_found(self, temp_repo: Path) -> None:
        config = NinjaConfig(bin_path="/nonexistent/binary")
        driver = NinjaDriver(config)

        result = driver.execute_sync(
            str(temp_repo),
            "test-step",
            {"task": "test"},
        )

        assert result.success is False
        assert "not found" in result.summary.lower()
        assert result.exit_code == -1

    @pytest.mark.asyncio
    async def test_execute_async_file_not_found(self, temp_repo: Path) -> None:
        config = NinjaConfig(bin_path="/nonexistent/binary")
        driver = NinjaDriver(config)

        result = await driver.execute_async(
            str(temp_repo),
            "test-step",
            {"task": "test"},
        )

        assert result.success is False
        assert "not found" in result.summary.lower()


class TestNinjaResult:
    """Tests for NinjaResult dataclass."""

    def test_default_values(self) -> None:
        result = NinjaResult(success=True, summary="Done")
        assert result.success is True
        assert result.summary == "Done"
        assert result.notes == ""
        assert result.suspected_touched_paths == []
        assert result.exit_code == 0
        assert result.model_used == ""

    def test_full_result(self) -> None:
        result = NinjaResult(
            success=False,
            summary="Failed",
            notes="Error details",
            suspected_touched_paths=["a.py", "b.py"],
            raw_logs_path="/tmp/log.txt",
            exit_code=1,
            stdout="output",
            stderr="error",
            model_used="anthropic/claude-sonnet-4",
        )

        assert result.success is False
        assert len(result.suspected_touched_paths) == 2
        assert result.exit_code == 1
        assert result.model_used == "anthropic/claude-sonnet-4"
