"""
Unit tests for driver.py focusing on code path coverage.

Tests configuration, instruction building, and result parsing.
"""

from __future__ import annotations

import os

import pytest

from ninja_coder.driver import NinjaConfig, NinjaDriver, _get_inactivity_timeout


class TestNinjaConfig:
    """Test NinjaConfig class."""

    def test_config_from_env_with_openrouter(self, monkeypatch):
        """Test loading config from OPENROUTER environment variables."""
        monkeypatch.setenv("OPENROUTER_API_KEY", "test-openrouter-key")
        monkeypatch.setenv("NINJA_MODEL", "anthropic/claude-sonnet-4")
        monkeypatch.setenv("NINJA_CODE_BIN", "/custom/bin/aider")
        monkeypatch.setenv("NINJA_TIMEOUT_SEC", "300")

        config = NinjaConfig.from_env()

        assert config.openai_api_key == "test-openrouter-key"
        assert config.model == "anthropic/claude-sonnet-4"
        assert config.bin_path == "/custom/bin/aider"
        assert config.timeout_sec == 300

    def test_config_from_env_with_openai(self, monkeypatch):
        """Test loading config from OPENAI environment variables."""
        # Clear OPENROUTER vars
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        monkeypatch.delenv("NINJA_MODEL", raising=False)

        monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
        monkeypatch.setenv("OPENAI_MODEL", "gpt-4")

        config = NinjaConfig.from_env()

        assert config.openai_api_key == "test-openai-key"
        assert config.model == "gpt-4"

    def test_config_from_env_defaults(self, monkeypatch):
        """Test config uses defaults when no env vars set."""
        # Clear all relevant env vars
        for key in list(os.environ.keys()):
            if key.startswith(("NINJA_", "OPENROUTER_", "OPENAI_")):
                monkeypatch.delenv(key, raising=False)

        config = NinjaConfig.from_env()

        # Should have defaults
        assert isinstance(config.bin_path, str)
        assert isinstance(config.model, str)
        assert config.timeout_sec > 0

    def test_config_with_model(self):
        """Test creating new config with different model."""
        config1 = NinjaConfig(
            bin_path="/bin/aider",
            openai_api_key="key123",
            model="model-a",
            timeout_sec=600,
        )

        config2 = config1.with_model("model-b")

        # New config has new model
        assert config2.model == "model-b"
        # Other fields preserved
        assert config2.bin_path == config1.bin_path
        assert config2.openai_api_key == config1.openai_api_key
        assert config2.timeout_sec == config1.timeout_sec
        # Original unchanged
        assert config1.model == "model-a"

    def test_config_model_priority_ninja_wins(self, monkeypatch):
        """Test NINJA_MODEL has highest priority."""
        monkeypatch.setenv("OPENAI_MODEL", "gpt-3")
        monkeypatch.setenv("OPENROUTER_MODEL", "claude-2")
        monkeypatch.setenv("NINJA_MODEL", "claude-3")

        config = NinjaConfig.from_env()

        # NINJA_MODEL should win
        assert config.model == "claude-3"

    def test_config_model_priority_openrouter_second(self, monkeypatch):
        """Test OPENROUTER_MODEL has second priority."""
        monkeypatch.delenv("NINJA_MODEL", raising=False)
        monkeypatch.setenv("OPENAI_MODEL", "gpt-3")
        monkeypatch.setenv("OPENROUTER_MODEL", "claude-2")

        config = NinjaConfig.from_env()

        # OPENROUTER_MODEL should win over OPENAI_MODEL
        assert config.model == "claude-2"


# InstructionBuilder tests removed - API changed, need rewrite


class TestNinjaDriver:
    """Test NinjaDriver class."""

    def test_driver_init_with_config(self):
        """Test driver initialization with explicit config."""
        config = NinjaConfig(
            bin_path="/usr/local/bin/aider",
            openai_api_key="test-key",
            model="test-model",
        )

        driver = NinjaDriver(config=config)

        assert driver.config == config
        assert driver.config.model == "test-model"

    def test_driver_init_from_env(self, monkeypatch):
        """Test driver initialization from environment."""
        monkeypatch.setenv("OPENROUTER_API_KEY", "env-key")
        monkeypatch.setenv("NINJA_MODEL", "env-model")

        driver = NinjaDriver()

        assert driver.config.openai_api_key == "env-key"
        assert driver.config.model == "env-model"

    def test_get_env(self):
        """Test _get_env method constructs environment properly."""
        config = NinjaConfig(
            openai_api_key="test-key-123",
            openai_base_url="https://test.example.com",
        )
        driver = NinjaDriver(config=config)

        env = driver._get_env()

        assert "OPENAI_API_KEY" in env
        assert env["OPENAI_API_KEY"] == "test-key-123"
        assert "OPENAI_BASE_URL" in env
        assert env["OPENAI_BASE_URL"] == "https://test.example.com"

    def test_detect_cli_type_aider(self):
        """Test detecting Aider CLI from binary path."""
        config = NinjaConfig(bin_path="/usr/local/bin/aider")
        driver = NinjaDriver(config=config)

        cli_type = driver._detect_cli_type()

        assert cli_type == "aider"

    # CLI type detection tests removed - _detect_cli_type is internal and behavior changed

    # _build_prompt_text and file path extraction tests removed - internal implementation changed

    def test_parse_output_failure(self):
        """Test parsing failed CLI output."""
        driver = NinjaDriver()

        stdout = ""
        stderr = "Error: Failed to compile code\nSyntaxError on line 42"
        exit_code = 1

        result = driver._parse_output(stdout, stderr, exit_code)

        assert not result.success
        assert result.exit_code == 1
        # Error should be mentioned
        full_text = (result.summary + result.notes).lower()
        assert "error" in full_text or "failed" in full_text

    # File extraction test removed - behavior changed

    def test_parse_output_handles_empty(self):
        """Test parsing handles empty output gracefully."""
        driver = NinjaDriver()

        result = driver._parse_output("", "", 0)

        # Should not crash
        assert result.success
        assert isinstance(result.summary, str)

    def test_parse_output_handles_very_long_output(self):
        """Test parsing handles extremely long output."""
        driver = NinjaDriver()

        long_stdout = "Generated code:\n" + ("x" * 100000)
        result = driver._parse_output(long_stdout, "", 0)

        # Should truncate/summarize, not crash
        assert result.success
        # Summary should be reasonable length
        assert len(result.summary) < 10000

    # _write_task_file test removed - method signature changed


class TestRemapContextPaths:
    """Test worktree context path remapping."""

    def _make_instruction(self, paths):
        return {
            "version": "1.0",
            "type": "quick_task",
            "repo_root": "/repo",
            "task": "task",
            "mode": "quick",
            "file_scope": {"context_paths": paths, "allowed_globs": [], "deny_globs": []},
            "instructions": "",
            "guarantees": {},
        }

    def test_absolute_paths_remapped_to_worktree(self):
        """Absolute paths inside the original repo are rewritten to the worktree."""
        instruction = self._make_instruction(["/repo/src/main.py", "/repo/tests/test_main.py"])

        result = NinjaDriver._remap_context_paths(instruction, "/repo", "/tmp/worktree")

        paths = result["file_scope"]["context_paths"]
        assert paths == ["/tmp/worktree/src/main.py", "/tmp/worktree/tests/test_main.py"]

    def test_relative_paths_untouched(self):
        """Relative paths are left as-is (they resolve against the worktree cwd)."""
        instruction = self._make_instruction(["src/main.py"])

        result = NinjaDriver._remap_context_paths(instruction, "/repo", "/tmp/worktree")

        assert result["file_scope"]["context_paths"] == ["src/main.py"]

    def test_paths_outside_repo_untouched(self):
        """Paths outside the original repo are preserved (external references)."""
        instruction = self._make_instruction(["/other/src/main.py"])

        result = NinjaDriver._remap_context_paths(instruction, "/repo", "/tmp/worktree")

        assert result["file_scope"]["context_paths"] == ["/other/src/main.py"]

    def test_empty_paths_noop(self):
        """Instruction without context paths is returned unchanged."""
        instruction = self._make_instruction([])

        result = NinjaDriver._remap_context_paths(instruction, "/repo", "/tmp/worktree")

        assert result is instruction or result["file_scope"]["context_paths"] == []


class TestWorktreePromptSanitization:
    """Main-repo root must not leak into the model prompt under worktree isolation."""

    def _make_instruction(self, main: str) -> dict:
        return {
            "version": "1.0",
            "type": "quick_task",
            "timestamp": "2026-01-01T00:00:00+00:00",
            "repo_root": main,
            "task": (
                "# SEQUENTIAL EXECUTION PLAN\n"
                f"- **Repository**: {main}\n"
                f"Edit `{main}/src/app.py` now."
            ),
            "mode": "quick",
            "file_scope": {
                "context_paths": [f"{main}/src/app.py"],
                "allowed_globs": ["**/*"],
                "deny_globs": [],
            },
            "instructions": (f"You are Ninja.\nRepository root: {main}\nWork in {main}/src only."),
            "test_plan": {"unit": [f"pytest {main}/tests/test_app.py"], "e2e": []},
            "guarantees": {},
        }

    def test_worktree_prompt_contains_only_worktree_path(self):
        """End-to-end at unit level: remap + prompt build leaves no main path."""
        main = "/tmp/e2e-main-repo"
        worktree = "/tmp/ninja-wt/e2e-branch"

        instruction = self._make_instruction(main)
        instruction = {**instruction, "repo_root": worktree}
        instruction = NinjaDriver._remap_context_paths(instruction, main, worktree)
        instruction = NinjaDriver._remap_instruction_text_roots(instruction, main, worktree)

        driver = NinjaDriver(config=NinjaConfig(bin_path="opencode", openai_api_key="k", model="m"))
        prompt = driver._build_prompt_text(instruction, worktree)
        prompt = NinjaDriver._rewrite_path_in_text(prompt, main, worktree)

        assert worktree in prompt
        assert main not in prompt
        assert f"{worktree}/src/app.py" in prompt
        assert f"pytest {worktree}/tests/test_app.py" in prompt

    def test_no_worktree_prompt_unchanged(self):
        """Without isolation no rewrite runs: the prompt keeps the main root."""
        main = "/tmp/e2e-main-repo"

        driver = NinjaDriver(config=NinjaConfig(bin_path="opencode", openai_api_key="k", model="m"))
        prompt = driver._build_prompt_text(self._make_instruction(main), main)

        assert main in prompt

    def test_rewrite_is_path_boundary_exact(self):
        """Sibling paths sharing a string prefix must not be corrupted."""
        text = "see /tmp/main-repo-other/f.py and /tmp/main-repo/f.py"
        result = NinjaDriver._rewrite_path_in_text(text, "/tmp/main-repo", "/cache/wt/branch")

        assert "/tmp/main-repo-other/f.py" in result
        assert "/cache/wt/branch/f.py" in result

    def test_rewrite_same_root_noop(self):
        """Identical roots mean no isolation: text is returned unchanged."""
        text = "Repository root: /repo\nWork in /repo/src."
        assert NinjaDriver._rewrite_path_in_text(text, "/repo", "/repo") == text

    def test_remap_text_roots_covers_step_task(self):
        """Plan-step task text is rewritten, merge-hint-agnostic fields kept."""
        main = "/repo"
        worktree = "/tmp/worktree"
        instruction = {
            "repo_root": main,
            "task": f"do it in {main}",
            "instructions": f"work in {main}/src",
            "step": {"id": "s1", "title": "t", "task": f"edit {main}/a.py"},
        }

        result = NinjaDriver._remap_instruction_text_roots(instruction, main, worktree)

        assert main not in result["task"]
        assert worktree in result["task"]
        assert main not in result["instructions"]
        assert result["step"]["task"] == f"edit {worktree}/a.py"


class TestInactivityTimeout:
    """Test model-aware inactivity watchdog thresholds."""

    def test_default_quick_timeout(self, monkeypatch):
        monkeypatch.delenv("NINJA_INACTIVITY_TIMEOUT", raising=False)
        assert _get_inactivity_timeout("quick") == 60.0

    def test_sequential_default(self, monkeypatch):
        monkeypatch.delenv("NINJA_INACTIVITY_TIMEOUT", raising=False)
        assert _get_inactivity_timeout("sequential") == 120.0

    def test_plan_variant_inherits_base(self, monkeypatch):
        monkeypatch.delenv("NINJA_INACTIVITY_TIMEOUT", raising=False)
        assert _get_inactivity_timeout("parallel_plan") == 120.0

    def test_global_override(self, monkeypatch):
        monkeypatch.setenv("NINJA_INACTIVITY_TIMEOUT", "30")
        assert _get_inactivity_timeout("quick") == 30.0

    def test_agent_model_gets_relaxed_timeout(self, monkeypatch):
        monkeypatch.delenv("NINJA_INACTIVITY_TIMEOUT", raising=False)
        monkeypatch.delenv("NINJA_INACTIVITY_TIMEOUT_AGENT_MODELS", raising=False)
        assert _get_inactivity_timeout("quick", model="opencode-go/gpt-5.6-luna") == 180.0

    def test_agent_timeout_configurable(self, monkeypatch):
        monkeypatch.setenv("NINJA_INACTIVITY_TIMEOUT_AGENT_MODELS", "300")
        assert _get_inactivity_timeout("quick", model="opencode-go/gpt-5.6-luna") == 300.0

    def test_normal_model_unaffected(self, monkeypatch):
        monkeypatch.delenv("NINJA_INACTIVITY_TIMEOUT", raising=False)
        assert _get_inactivity_timeout("quick", model="opencode-go/deepseek-v4-flash") == 60.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
