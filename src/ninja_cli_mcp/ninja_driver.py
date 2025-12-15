"""
Ninja Code CLI driver.

This module handles all interactions with the AI code CLI binary.
It constructs instruction documents and manages subprocess execution.

IMPORTANT: This is the only module that launches the AI code CLI.
The MCP server never directly reads/writes user project files.

Supports any OpenRouter-compatible model including:
- Qwen models (qwen/qwen3-coder, qwen/qwen-2.5-coder-32b-instruct, etc.)
- Claude models (anthropic/claude-3.5-sonnet, anthropic/claude-3-opus, etc.)
- GPT models (openai/gpt-4o, openai/gpt-4-turbo, etc.)
- DeepSeek models (deepseek/deepseek-coder, deepseek/deepseek-chat, etc.)
- And many more via OpenRouter
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ninja_cli_mcp.logging_utils import TaskLogger, create_task_logger, get_logger
from ninja_cli_mcp.models import ExecutionMode, PlanStep
from ninja_cli_mcp.path_utils import ensure_internal_dirs, safe_join


logger = get_logger(__name__)


# Popular OpenRouter models for code tasks
RECOMMENDED_MODELS = {
    # Qwen models
    "qwen/qwen3-coder": "Qwen3 Coder - optimized for code generation",
    "qwen/qwen-2.5-coder-32b-instruct": "Qwen 2.5 Coder 32B - large coding model",
    # Claude models
    "anthropic/claude-sonnet-4": "Claude Sonnet 4 - excellent for complex code",
    "anthropic/claude-3.5-sonnet": "Claude 3.5 Sonnet - fast and capable",
    # GPT models
    "openai/gpt-4o": "GPT-4o - OpenAI's flagship model",
    "openai/gpt-4-turbo": "GPT-4 Turbo - fast GPT-4 variant",
    # DeepSeek models
    "deepseek/deepseek-coder": "DeepSeek Coder - specialized for code",
    "deepseek/deepseek-chat": "DeepSeek Chat - general purpose",
    # Other popular models
    "google/gemini-pro-1.5": "Gemini Pro 1.5 - Google's advanced model",
    "meta-llama/llama-3.1-70b-instruct": "Llama 3.1 70B - Meta's open model",
}

DEFAULT_MODEL = "anthropic/claude-sonnet-4"


@dataclass
class NinjaConfig:
    """Configuration for Ninja Code CLI."""

    bin_path: str = "ninja-code"
    openai_base_url: str = "https://openrouter.ai/api/v1"
    openai_api_key: str = ""
    model: str = DEFAULT_MODEL
    timeout_sec: int = 600

    @classmethod
    def from_env(cls) -> "NinjaConfig":
        """Create config from environment variables."""
        api_key = os.environ.get("OPENROUTER_API_KEY") or os.environ.get("OPENAI_API_KEY", "")

        # Model priority: NINJA_MODEL > OPENROUTER_MODEL > OPENAI_MODEL > default
        model = (
            os.environ.get("NINJA_MODEL")
            or os.environ.get("OPENROUTER_MODEL")
            or os.environ.get("OPENAI_MODEL")
            or DEFAULT_MODEL
        )

        return cls(
            bin_path=os.environ.get("NINJA_CODE_BIN", "ninja-code"),
            openai_base_url=os.environ.get("OPENAI_BASE_URL", "https://openrouter.ai/api/v1"),
            openai_api_key=api_key,
            model=model,
            timeout_sec=int(os.environ.get("NINJA_TIMEOUT_SEC", "600")),
        )

    def with_model(self, model: str) -> "NinjaConfig":
        """Create a new config with a different model."""
        return NinjaConfig(
            bin_path=self.bin_path,
            openai_base_url=self.openai_base_url,
            openai_api_key=self.openai_api_key,
            model=model,
            timeout_sec=self.timeout_sec,
        )


@dataclass
class NinjaResult:
    """Result from Ninja Code CLI execution."""

    success: bool
    summary: str
    notes: str = ""
    suspected_touched_paths: list[str] = field(default_factory=list)
    raw_logs_path: str = ""
    exit_code: int = 0
    stdout: str = ""
    stderr: str = ""
    model_used: str = ""


class InstructionBuilder:
    """
    Builds instruction documents for the AI code CLI.

    The instruction document tells the AI code CLI what to do,
    including the task, file scope, and execution mode.
    """

    def __init__(
        self,
        repo_root: str,
        mode: ExecutionMode = ExecutionMode.QUICK,
    ):
        """
        Initialize instruction builder.

        Args:
            repo_root: Repository root path.
            mode: Execution mode (quick or full).
        """
        self.repo_root = repo_root
        self.mode = mode

    def build_quick_task(
        self,
        task: str,
        context_paths: list[str],
        allowed_globs: list[str],
        deny_globs: list[str],
    ) -> dict[str, Any]:
        """
        Build instruction for a quick single-pass task.

        Args:
            task: Task description.
            context_paths: Paths to focus on.
            allowed_globs: Allowed file patterns.
            deny_globs: Denied file patterns.

        Returns:
            Instruction document as dict.
        """
        return {
            "version": "1.0",
            "type": "quick_task",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "repo_root": self.repo_root,
            "task": task,
            "mode": "quick",
            "file_scope": {
                "context_paths": context_paths,
                "allowed_globs": allowed_globs or ["**/*"],
                "deny_globs": deny_globs or [],
            },
            "instructions": self._build_quick_instructions(task, context_paths),
            "guarantees": self._build_guarantees(),
        }

    def build_plan_step(
        self,
        step: PlanStep,
        global_allowed_globs: list[str],
        global_deny_globs: list[str],
    ) -> dict[str, Any]:
        """
        Build instruction for a plan step.

        Args:
            step: Plan step to execute.
            global_allowed_globs: Global allowed patterns.
            global_deny_globs: Global denied patterns.

        Returns:
            Instruction document as dict.
        """
        # Merge step-level and global globs
        allowed = list(set(step.allowed_globs + global_allowed_globs)) or ["**/*"]
        denied = list(set(step.deny_globs + global_deny_globs))

        return {
            "version": "1.0",
            "type": "plan_step",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "repo_root": self.repo_root,
            "step": {
                "id": step.id,
                "title": step.title,
                "task": step.task,
            },
            "mode": self.mode.value,
            "file_scope": {
                "context_paths": step.context_paths,
                "allowed_globs": allowed,
                "deny_globs": denied,
            },
            "test_plan": {
                "unit": step.test_plan.unit,
                "e2e": step.test_plan.e2e,
            },
            "constraints": {
                "max_iterations": step.max_iterations,
                "max_tokens": step.constraints.max_tokens,
                "time_budget_sec": step.constraints.time_budget_sec,
            },
            "instructions": self._build_step_instructions(step),
            "guarantees": self._build_guarantees(),
        }

    def build_test_task(
        self,
        commands: list[str],
        timeout_sec: int,
    ) -> dict[str, Any]:
        """
        Build instruction for running tests.

        Args:
            commands: Test commands to run.
            timeout_sec: Timeout in seconds.

        Returns:
            Instruction document as dict.
        """
        return {
            "version": "1.0",
            "type": "test_task",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "repo_root": self.repo_root,
            "task": "Run the specified test commands and report results",
            "test_commands": commands,
            "timeout_sec": timeout_sec,
            "instructions": self._build_test_instructions(commands),
            "guarantees": self._build_guarantees(),
        }

    def _build_quick_instructions(self, task: str, context_paths: list[str]) -> str:
        """Build instruction text for quick mode."""
        paths_text = ", ".join(context_paths) if context_paths else "the repository"

        return f"""You are an AI code assistant operating in QUICK mode.

TASK: {task}

FOCUS AREA: {paths_text}

YOUR RESPONSIBILITIES:
1. Read the relevant source files to understand the context
2. Make the necessary code changes to complete the task
3. Create new files if needed
4. Run quick sanity checks (linter, type check) if appropriate
5. Stay within the allowed file scope

EXECUTION MODE: Single pass - implement the change efficiently without extensive review cycles.

You have full read/write access to files within the allowed scope.
The orchestrator will NOT inspect or modify source files itself.
You are the sole executor of code changes."""

    def _build_step_instructions(self, step: PlanStep) -> str:
        """Build instruction text for plan step execution."""
        if self.mode == ExecutionMode.QUICK:
            pipeline = "Single coder pass"
            extra = ""
        else:
            pipeline = "Full pipeline: coder -> reviewer -> tester -> fix loop -> final review"
            extra = f"""
ITERATION BUDGET: Up to {step.max_iterations} fix iterations if tests fail.

TEST COMMANDS TO RUN:
- Unit tests: {", ".join(step.test_plan.unit) if step.test_plan.unit else "None specified"}
- E2E tests: {", ".join(step.test_plan.e2e) if step.test_plan.e2e else "None specified"}

After implementing, you MUST:
1. Self-review your changes
2. Run the specified tests
3. If tests fail, analyze and fix (up to {step.max_iterations} iterations)
4. Perform a final review before completing"""

        paths_text = ", ".join(step.context_paths) if step.context_paths else "the repository"

        return f"""You are an AI code assistant executing plan step: {step.title}

STEP ID: {step.id}
TASK: {step.task}

FOCUS AREA: {paths_text}

EXECUTION PIPELINE: {pipeline}
{extra}

YOUR RESPONSIBILITIES:
1. Read relevant source files to understand context
2. Implement the required changes
3. Create new files if needed
4. Validate your changes according to the execution mode
5. Stay within the allowed file scope

You have full read/write access to files within the allowed scope.
The orchestrator will NOT inspect or modify source files itself.
You are the sole executor of code changes."""

    def _build_test_instructions(self, commands: list[str]) -> str:
        """Build instruction text for test execution."""
        cmd_list = "\n".join(f"  - {cmd}" for cmd in commands)

        return f"""You are an AI code assistant executing test commands.

TEST COMMANDS:
{cmd_list}

YOUR RESPONSIBILITIES:
1. Change to the repository root directory
2. Run each test command in sequence
3. Capture and report the output
4. Report pass/fail status for each command
5. Provide a summary of test results

You have access to run commands and read files as needed for testing."""

    def _build_guarantees(self) -> dict[str, str]:
        """Build guarantee statements."""
        return {
            "file_access": "You (AI assistant) are responsible for all file read/write operations",
            "orchestrator_role": "The orchestrator will NOT inspect or modify source files",
            "scope_enforcement": "You must respect the allowed_globs and deny_globs constraints",
            "test_execution": "You are responsible for running any specified tests",
        }


class NinjaDriver:
    """
    Driver for executing tasks via Ninja Code CLI.

    This class manages the subprocess lifecycle and result parsing.
    Supports any OpenRouter-compatible model.
    """

    def __init__(self, config: NinjaConfig | None = None):
        """
        Initialize the driver.

        Args:
            config: Ninja CLI configuration. If None, loads from env.
        """
        self.config = config or NinjaConfig.from_env()

    def _get_env(self) -> dict[str, str]:
        """Get environment variables for Ninja Code CLI subprocess."""
        env = os.environ.copy()
        env["OPENAI_BASE_URL"] = self.config.openai_base_url
        env["OPENAI_API_KEY"] = self.config.openai_api_key
        env["OPENAI_MODEL"] = self.config.model
        return env

    def _write_task_file(
        self,
        repo_root: str,
        step_id: str,
        instruction: dict[str, Any],
    ) -> Path:
        """
        Write instruction document to a task file.

        Args:
            repo_root: Repository root path.
            step_id: Step identifier.
            instruction: Instruction document.

        Returns:
            Path to the task file.
        """
        dirs = ensure_internal_dirs(repo_root)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        safe_id = "".join(c if c.isalnum() or c in "-_" else "_" for c in step_id)

        task_file = safe_join(dirs["tasks"], f"{timestamp}_{safe_id}.json")

        # Add model info to instruction
        instruction["model"] = self.config.model

        with open(task_file, "w") as f:
            json.dump(instruction, f, indent=2)

        return task_file

    def _build_command(self, task_file: Path, repo_root: str) -> list[str]:
        """
        Build the command to run Ninja Code CLI.

        Args:
            task_file: Path to the task file.
            repo_root: Repository root path.

        Returns:
            Command as list of strings.
        """
        # Strategy pattern: try different invocation methods
        # Primary: task file mode (if CLI supports it)
        # Fallback: prompt mode with instruction as argument

        # Read the instruction to build a prompt
        with open(task_file) as f:
            instruction = json.load(f)

        # Build a comprehensive prompt from the instruction
        prompt_parts = [
            instruction.get("instructions", ""),
            "",
            "=== FILE SCOPE ===",
            f"Repository root: {instruction.get('repo_root', repo_root)}",
        ]

        file_scope = instruction.get("file_scope", {})
        if file_scope.get("context_paths"):
            prompt_parts.append(f"Focus paths: {', '.join(file_scope['context_paths'])}")
        if file_scope.get("allowed_globs"):
            prompt_parts.append(f"Allowed patterns: {', '.join(file_scope['allowed_globs'])}")
        if file_scope.get("deny_globs"):
            prompt_parts.append(f"Denied patterns: {', '.join(file_scope['deny_globs'])}")

        # Add test plan if present
        test_plan = instruction.get("test_plan", {})
        if test_plan.get("unit") or test_plan.get("e2e"):
            prompt_parts.append("")
            prompt_parts.append("=== TEST PLAN ===")
            if test_plan.get("unit"):
                prompt_parts.append(f"Unit tests: {', '.join(test_plan['unit'])}")
            if test_plan.get("e2e"):
                prompt_parts.append(f"E2E tests: {', '.join(test_plan['e2e'])}")

        prompt = "\n".join(prompt_parts)

        # Build command - using prompt mode as primary method
        # CLI interface is assumed to support:
        # ninja-code --prompt "..." --cwd /path/to/repo --yes
        cmd = [
            self.config.bin_path,
            "--prompt",
            prompt,
            "--cwd",
            repo_root,
            "--yes",  # Non-interactive mode
        ]

        return cmd

    def _parse_output(self, stdout: str, stderr: str, exit_code: int) -> NinjaResult:
        """
        Parse Ninja Code CLI output to extract results.

        Args:
            stdout: Standard output.
            stderr: Standard error.
            exit_code: Process exit code.

        Returns:
            Parsed result.
        """
        success = exit_code == 0

        # Try to extract summary from output
        summary = "Task completed" if success else "Task failed"
        notes = ""
        suspected_paths: list[str] = []

        # Look for common patterns in output that indicate file changes
        # This is best-effort extraction
        file_patterns = [
            r"(?:wrote|created|modified|updated|edited)\s+['\"]?([^\s'\"]+)['\"]?",
            r"(?:writing|creating|modifying|updating|editing)\s+['\"]?([^\s'\"]+)['\"]?",
            r"file:\s*['\"]?([^\s'\"]+)['\"]?",
        ]

        combined_output = stdout + "\n" + stderr
        for pattern in file_patterns:
            matches = re.findall(pattern, combined_output, re.IGNORECASE)
            for match in matches:
                if match and ("/" in match or "." in match):
                    suspected_paths.append(match)

        # Deduplicate paths
        suspected_paths = list(set(suspected_paths))

        # Try to extract summary from structured output if present
        # Look for JSON in output
        try:
            json_match = re.search(r'\{[^{}]*"summary"[^{}]*\}', combined_output)
            if json_match:
                result_json = json.loads(json_match.group())
                summary = result_json.get("summary", summary)
                notes = result_json.get("notes", notes)
        except (json.JSONDecodeError, AttributeError):
            pass

        # If no structured summary, try to extract first meaningful line
        if summary in ("Task completed", "Task failed"):
            lines = [line.strip() for line in combined_output.split("\n") if line.strip()]
            # Skip typical CLI output lines
            skip_prefixes = ("$", ">", "#", "debug:", "info:", "[", "loading", "starting")
            for line in lines[-10:]:  # Check last 10 lines
                lower = line.lower()
                if not any(lower.startswith(p) for p in skip_prefixes):
                    if len(line) < 200:  # Reasonable summary length
                        summary = line
                        break

        if not success and stderr:
            notes = stderr[:500] if len(stderr) > 500 else stderr

        return NinjaResult(
            success=success,
            summary=summary,
            notes=notes,
            suspected_touched_paths=suspected_paths,
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            model_used=self.config.model,
        )

    def execute_sync(
        self,
        repo_root: str,
        step_id: str,
        instruction: dict[str, Any],
        timeout_sec: int | None = None,
    ) -> NinjaResult:
        """
        Execute a task synchronously.

        Args:
            repo_root: Repository root path.
            step_id: Step identifier.
            instruction: Instruction document.
            timeout_sec: Timeout in seconds.

        Returns:
            Execution result.
        """
        task_logger = create_task_logger(repo_root, step_id)
        task_logger.info(f"Starting task execution with model: {self.config.model}")
        task_logger.set_metadata("instruction", instruction)
        task_logger.set_metadata("model", self.config.model)

        try:
            # Write task file
            task_file = self._write_task_file(repo_root, step_id, instruction)
            task_logger.info(f"Wrote task file: {task_file}")

            # Build command
            cmd = self._build_command(task_file, repo_root)
            task_logger.info(f"Running command: {' '.join(cmd)}")

            # Get environment
            env = self._get_env()

            # Execute
            timeout = timeout_sec or self.config.timeout_sec
            process = subprocess.run(
                cmd,
                cwd=repo_root,
                env=env,
                capture_output=True,
                text=True,
                timeout=timeout,
            )

            task_logger.log_subprocess(cmd, process.returncode, process.stdout, process.stderr)

            # Parse result
            result = self._parse_output(process.stdout, process.stderr, process.returncode)
            result.raw_logs_path = task_logger.save()

            task_logger.info(
                f"Task {'succeeded' if result.success else 'failed'}: {result.summary}"
            )

            return result

        except subprocess.TimeoutExpired:
            task_logger.error(f"Task timed out after {timeout_sec or self.config.timeout_sec}s")
            logs_path = task_logger.save()
            return NinjaResult(
                success=False,
                summary="Task timed out",
                notes=f"Execution exceeded {timeout_sec or self.config.timeout_sec}s timeout",
                raw_logs_path=logs_path,
                exit_code=-1,
                model_used=self.config.model,
            )
        except FileNotFoundError:
            task_logger.error(f"Ninja Code CLI not found: {self.config.bin_path}")
            logs_path = task_logger.save()
            return NinjaResult(
                success=False,
                summary="Ninja Code CLI not found",
                notes=f"Could not find executable: {self.config.bin_path}. "
                f"Install Ninja Code CLI or set NINJA_CODE_BIN environment variable.",
                raw_logs_path=logs_path,
                exit_code=-1,
                model_used=self.config.model,
            )
        except Exception as e:
            task_logger.error(f"Unexpected error: {e}")
            logs_path = task_logger.save()
            return NinjaResult(
                success=False,
                summary="Execution error",
                notes=str(e),
                raw_logs_path=logs_path,
                exit_code=-1,
                model_used=self.config.model,
            )

    async def execute_async(
        self,
        repo_root: str,
        step_id: str,
        instruction: dict[str, Any],
        timeout_sec: int | None = None,
    ) -> NinjaResult:
        """
        Execute a task asynchronously.

        Args:
            repo_root: Repository root path.
            step_id: Step identifier.
            instruction: Instruction document.
            timeout_sec: Timeout in seconds.

        Returns:
            Execution result.
        """
        task_logger = create_task_logger(repo_root, step_id)
        task_logger.info(f"Starting async task execution with model: {self.config.model}")
        task_logger.set_metadata("instruction", instruction)
        task_logger.set_metadata("model", self.config.model)

        try:
            # Write task file
            task_file = self._write_task_file(repo_root, step_id, instruction)
            task_logger.info(f"Wrote task file: {task_file}")

            # Build command
            cmd = self._build_command(task_file, repo_root)
            task_logger.info(f"Running command: {' '.join(cmd)}")

            # Get environment
            env = self._get_env()

            # Execute asynchronously
            timeout = timeout_sec or self.config.timeout_sec

            process = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=repo_root,
                env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    process.communicate(),
                    timeout=timeout,
                )
                stdout = stdout_bytes.decode() if stdout_bytes else ""
                stderr = stderr_bytes.decode() if stderr_bytes else ""
                exit_code = process.returncode or 0

            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                task_logger.error(f"Task timed out after {timeout}s")
                logs_path = task_logger.save()
                return NinjaResult(
                    success=False,
                    summary="Task timed out",
                    notes=f"Execution exceeded {timeout}s timeout",
                    raw_logs_path=logs_path,
                    exit_code=-1,
                    model_used=self.config.model,
                )

            task_logger.log_subprocess(cmd, exit_code, stdout, stderr)

            # Parse result
            result = self._parse_output(stdout, stderr, exit_code)
            result.raw_logs_path = task_logger.save()

            task_logger.info(
                f"Task {'succeeded' if result.success else 'failed'}: {result.summary}"
            )

            return result

        except FileNotFoundError:
            task_logger.error(f"Ninja Code CLI not found: {self.config.bin_path}")
            logs_path = task_logger.save()
            return NinjaResult(
                success=False,
                summary="Ninja Code CLI not found",
                notes=f"Could not find executable: {self.config.bin_path}. "
                f"Install Ninja Code CLI or set NINJA_CODE_BIN environment variable.",
                raw_logs_path=logs_path,
                exit_code=-1,
                model_used=self.config.model,
            )
        except Exception as e:
            task_logger.error(f"Unexpected error: {e}")
            logs_path = task_logger.save()
            return NinjaResult(
                success=False,
                summary="Execution error",
                notes=str(e),
                raw_logs_path=logs_path,
                exit_code=-1,
                model_used=self.config.model,
            )


# Backwards compatibility aliases
QwenConfig = NinjaConfig
QwenResult = NinjaResult
QwenDriver = NinjaDriver
