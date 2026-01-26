"""
Ninja Code CLI driver for the Coder module.

This module handles all interactions with the AI code CLI binary.
It constructs instruction documents and manages subprocess execution.

IMPORTANT: This module is the only module that launches the AI code CLI.
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
import tempfile
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from ninja_coder.model_selector import ModelSelector
from ninja_coder.models import (
    ExecutionMode,
    PlanStep,
    TaskComplexity,
)
from ninja_coder.sessions import SessionManager
from pydantic import Field
from ninja_coder.safety import validate_task_safety
from ninja_coder.strategies import CLIStrategyRegistry
from ninja_common.defaults import (
    DEFAULT_CODE_BIN,
    DEFAULT_CODER_MODEL,
    DEFAULT_OPENAI_BASE_URL,
    DEFAULT_TIMEOUT_SEC,
    FALLBACK_CODER_MODELS,
)
from ninja_common.logging_utils import create_task_logger, get_logger
from ninja_common.path_utils import ensure_internal_dirs, safe_join


logger = get_logger(__name__)


@dataclass
class NinjaConfig:
    """Configuration for Ninja Code CLI."""

    bin_path: str = DEFAULT_CODE_BIN
    openai_base_url: str = DEFAULT_OPENAI_BASE_URL
    openai_api_key: str = ""
    model: str = DEFAULT_CODER_MODEL
    timeout_sec: int = DEFAULT_TIMEOUT_SEC

    @classmethod
    def from_env(cls) -> NinjaConfig:
        """Create config from environment variables."""
        api_key = os.environ.get("OPENROUTER_API_KEY") or os.environ.get("OPENAI_API_KEY", "")

        # Model priority: NINJA_MODEL > OPENROUTER_MODEL > OPENAI_MODEL > default
        model = (
            os.environ.get("NINJA_MODEL")
            or os.environ.get("OPENROUTER_MODEL")
            or os.environ.get("OPENAI_MODEL")
            or DEFAULT_CODER_MODEL
        )

        return cls(
            bin_path=os.environ.get("NINJA_CODE_BIN", DEFAULT_CODE_BIN),
            openai_base_url=os.environ.get("OPENAI_BASE_URL", DEFAULT_OPENAI_BASE_URL),
            openai_api_key=api_key,
            model=model,
            timeout_sec=int(os.environ.get("NINJA_TIMEOUT_SEC", str(DEFAULT_TIMEOUT_SEC))),
        )

    def with_model(self, model: str) -> NinjaConfig:
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
    aider_error_detected: bool = False  # Flag for aider-specific internal errors
    session_id: str | None = None  # Session ID if session was used


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
            "timestamp": datetime.now(UTC).isoformat(),
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
        conversation_history: list[dict[str, str]] | None = None,
    ) -> dict[str, Any]:
        """
        Build instruction for a plan step.

        Args:
            step: Plan step to execute.
            global_allowed_globs: Global allowed patterns.
            global_deny_globs: Global denied patterns.
            conversation_history: Optional conversation history for dialogue mode.

        Returns:
            Instruction document as dict.
        """
        # Merge step-level and global globs
        allowed = list(set(step.allowed_globs + global_allowed_globs)) or ["**/*"]
        denied = list(set(step.deny_globs + global_deny_globs))

        step_dict = {
            "id": step.id,
            "title": step.title,
            "task": step.task,
        }

        # Build instruction dict
        instruction = {
            "version": "1.0",
            "type": "plan_step",
            "timestamp": datetime.now(UTC).isoformat(),
            "repo_root": self.repo_root,
            "step": step_dict,
            "mode": self.mode.value,
            "file_scope": {
                "context_paths": step.context_paths,
                "allowed_globs": allowed,
                "deny_globs": denied,
            },
            "instructions": self._build_step_instructions(step),
            "test_plan": {
                "unit": step.test_plan.unit,
                "e2e": step.test_plan.e2e,
            },
            "guarantees": self._build_guarantees(),
        }

        # Add conversation history if provided (for dialogue mode)
        if conversation_history:
            instruction["conversation_history"] = conversation_history

        return instruction

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
            "timestamp": datetime.now(UTC).isoformat(),
            "repo_root": self.repo_root,
            "task": "Run the specified test commands and report results",
            "test_commands": commands,
            "timeout_sec": timeout_sec,
            "instructions": self._build_test_instructions(commands),
            "guarantees": self._build_guarantees(),
        }

    def _build_quick_instructions(self, task: str, context_paths: list[str]) -> str:
        """Build instruction text for quick mode with reasoning prompt."""
        paths_text = ", ".join(context_paths) if context_paths else "the repository"

        return f"""You are Ninja, an AI code writing specialist.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🎯 YOUR TASK:
{task}

📂 FOCUS AREA: {paths_text}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🧠 REASONING PHASE (spend tokens thinking):

Before writing ANY code, think through:

1. UNDERSTANDING:
   - What exactly is being asked?
   - What are the key requirements?
   - What files need to be created/modified?

2. CONTEXT ANALYSIS:
   - What existing code is relevant?
   - What patterns/conventions are used in this codebase?
   - What dependencies/imports are needed?

3. IMPLEMENTATION PLAN:
   - What's the logical order of changes?
   - What edge cases need handling?
   - What validation/error handling is needed?

4. QUALITY CHECKS:
   - Are type hints needed?
   - Are docstrings needed?
   - Does this follow the codebase style?

5. TEST COVERAGE:
   - What unit tests are needed for this code?
   - What test cases cover the main functionality?
   - What edge cases should be tested?

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

✅ YOUR RESPONSIBILITIES:
1. Read relevant source files to understand context
2. Think through the implementation (use reasoning above)
3. Write clean, well-structured code
4. Create new files if needed
5. Add type hints and docstrings where appropriate
6. **WRITE UNIT TESTS** for all new/modified code
7. Stay within the allowed file scope

🧪 TESTING REQUIREMENTS:
   • ALWAYS write unit tests for new functions/classes/methods
   • Place tests in appropriate test files (tests/ directory or alongside code)
   • Follow existing test patterns in the codebase
   • Cover main functionality and edge cases
   • Use appropriate test framework (pytest, unittest, etc.)
   • Include docstrings in test functions explaining what they test

⚠️  EXECUTION MODE: Single pass - implement efficiently and correctly.

🔒 SCOPE: You have full read/write access within allowed file patterns.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

💡 REMEMBER:
   • Think before coding (reasoning phase)
   • Write quality code, not quick hacks
   • Follow existing patterns in the codebase
   • **ALWAYS include unit tests** - untested code is incomplete
   • The orchestrator will NOT see your code, only a summary
   • Make your changes count - this is a single pass

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"""

    def _build_step_instructions(self, step: PlanStep) -> str:
        """Build instruction text for plan step execution with reasoning."""
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

        return f"""You are Ninja, an AI code writing specialist executing: {step.title}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🎯 STEP ID: {step.id}

📋 TASK SPECIFICATION:
{step.task}

📂 FOCUS AREA: {paths_text}

⚙️  EXECUTION PIPELINE: {pipeline}
{extra}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🧠 REASONING PHASE (spend tokens thinking):

Before writing ANY code, think through:

1. UNDERSTANDING:
   - What exactly is this step asking for?
   - How does it fit into the larger plan?
   - What are the acceptance criteria?

2. CONTEXT ANALYSIS:
   - What code from previous steps is relevant?
   - What existing patterns should I follow?
   - What dependencies exist?

3. IMPLEMENTATION STRATEGY:
   - What's the best approach for this step?
   - What files need changes?
   - What's the logical order?

4. QUALITY & TESTING:
   - What edge cases exist?
   - What validation is needed?
   - How will this be tested?
   - What unit tests are required?

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

✅ YOUR RESPONSIBILITIES:
1. Read relevant source files to understand context
2. Think through the implementation (use reasoning above)
3. Implement the required changes with high quality
4. Create new files if needed
5. **WRITE UNIT TESTS** for all new/modified code
6. Validate according to the execution mode
7. Stay within the allowed file scope

🧪 TESTING REQUIREMENTS:
   • ALWAYS write unit tests for new functions/classes/methods
   • Place tests in appropriate test files (tests/ directory or alongside code)
   • Follow existing test patterns in the codebase
   • Cover main functionality and edge cases
   • Use appropriate test framework (pytest, unittest, etc.)
   • Include docstrings in test functions explaining what they test
   • Ensure tests are runnable and pass

🔒 SCOPE: You have full read/write access within allowed file patterns.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

💡 REMEMBER:
   • Think deeply before coding (reasoning phase)
   • This step is part of a larger plan - make it solid
   • **ALWAYS include unit tests** - untested code is incomplete
   • The orchestrator will NOT see your code, only a summary
   • Quality over speed - get it right

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"""

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
            "response_format": "Return ONLY a brief summary - the orchestrator does not need source code",
            "test_coverage": "You MUST write unit tests for all new/modified code - untested code is incomplete",
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

        # Get strategy based on binary path
        self._strategy = CLIStrategyRegistry.get_strategy(self.config.bin_path, self.config)

        # Initialize session manager
        from ninja_common.path_utils import get_cache_dir
        cache_dir = get_cache_dir()
        self.session_manager = SessionManager(cache_dir)

        logger.info(f"Initialized NinjaDriver with {self._strategy.name} strategy")

    def _get_env(self) -> dict[str, str]:
        """Get environment variables for Ninja Code CLI subprocess with security filtering."""
        env = os.environ.copy()

        # Set required environment variables
        env["OPENAI_BASE_URL"] = self.config.openai_base_url
        env["OPENAI_API_KEY"] = self.config.openai_api_key
        env["OPENAI_MODEL"] = self.config.model

        # Filter out potentially sensitive environment variables
        sensitive_patterns = [
            "KEY",
            "SECRET",
            "PASSWORD",
            "TOKEN",
            "CREDENTIAL",
            "AUTH",
            "PASS",
            "PWD",
            "API_",
            "PRIVATE",
        ]

        filtered_env = {}
        for key, value in env.items():
            # Always include required variables
            if key in ["OPENAI_BASE_URL", "OPENAI_API_KEY", "OPENAI_MODEL", "PATH", "HOME"]:
                filtered_env[key] = value
                continue

            # Filter out sensitive variables
            key_upper = key.upper()
            if not any(pattern in key_upper for pattern in sensitive_patterns):
                filtered_env[key] = value
            else:
                # Log that we're filtering a variable (but don't log the value)
                logger.debug(f"Filtering sensitive environment variable: {key}")

        return filtered_env

    def _write_task_file(
        self,
        repo_root: str,
        step_id: str,
        instruction: dict[str, Any],
    ) -> Path:
        """
        Write instruction document to a secure task file.

        Args:
            repo_root: Repository root path.
            step_id: Step identifier.
            instruction: Instruction document.

        Returns:
            Path to the task file.
        """
        dirs = ensure_internal_dirs(repo_root)
        timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        safe_id = "".join(c if c.isalnum() or c in "-_" else "_" for c in step_id)

        # Use secure temporary file creation
        task_file_path = safe_join(dirs["tasks"], f"{timestamp}_{safe_id}.json")

        # Create secure temporary file with restricted permissions
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".json",
            dir=dirs["tasks"],
            delete=False,
            prefix=f"{timestamp}_{safe_id}_",
        ) as tmp_file:
            # Add model info to instruction
            instruction["model"] = self.config.model
            json.dump(instruction, tmp_file, indent=2)
            tmp_file.flush()
            os.fsync(tmp_file.fileno())
            temp_path = Path(tmp_file.name)

        # Set secure permissions (read/write for owner only)
        Path(temp_path).chmod(0o600)

        # Atomically move to final location
        temp_path.rename(task_file_path)

        return task_file_path

    def _detect_cli_type(self) -> str:
        """
        Detect which type of CLI we're using based on the binary name.

        .. deprecated::
            Use self._strategy.name instead. This method is kept for backwards
            compatibility with existing tests but will be removed in a future version.

        Returns:
            CLI type: 'aider', 'qwen', 'claude', 'gemini', 'cursor', or 'generic'
        """
        bin_name = Path(self.config.bin_path).name.lower()
        if "aider" in bin_name:
            return "aider"
        elif "qwen" in bin_name:
            return "qwen"
        elif "claude" in bin_name:
            return "claude"
        elif "gemini" in bin_name:
            return "gemini"
        elif "cursor" in bin_name:
            return "cursor"
        else:
            return "generic"

    def _select_model_for_task(
        self,
        instruction: dict[str, Any],
        task_type: str = "quick",
    ) -> tuple[str, bool]:
        """Select best model for task using intelligent selection.

        Args:
            instruction: Instruction document with task details.
            task_type: Type of task ('quick', 'sequential', 'parallel').

        Returns:
            Tuple of (model_name, use_coding_plan_api).
        """
        # Determine task complexity
        if task_type == "parallel":
            complexity = TaskComplexity.PARALLEL
            fanout = instruction.get("parallel_context", {}).get("total_steps", 1)
        elif task_type == "sequential":
            complexity = TaskComplexity.SEQUENTIAL
            fanout = 1
        else:
            complexity = TaskComplexity.QUICK
            fanout = 1

        # Check environment overrides
        prefer_cost = os.environ.get("NINJA_PREFER_COST", "false").lower() == "true"
        prefer_quality = os.environ.get("NINJA_PREFER_QUALITY", "false").lower() == "true"

        # Select model using model selector directly
        model_selector = ModelSelector(default_model=self.config.model)
        recommendation = model_selector.select_model(
            complexity,
            fanout=fanout,
        )

        logger.info(
            f"Selected model: {recommendation.model} "
            f"(reason: {recommendation.reason}, "
            f"estimated cost: {recommendation.cost_estimate})"
        )

        return recommendation.model, recommendation.use_coding_plan_api

    def _build_prompt_text(self, instruction: dict[str, Any], repo_root: str) -> str:
        """
        Build a comprehensive prompt from the instruction document.

        Args:
            instruction: Instruction document.
            repo_root: Repository root path.

        Returns:
            Formatted prompt text.
        """
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

        return "\n".join(prompt_parts)

    def _build_command_claude(
        self,
        prompt: str,
        repo_root: str,
        file_paths: list[str] | None = None,
    ) -> list[str]:
        """Build command for Claude CLI with secure argument handling.

        Args:
            prompt: The instruction prompt.
            repo_root: Repository root path (used for working directory context).
            file_paths: List of file paths to include in the prompt context.
        """
        cmd = [
            self.config.bin_path,
            "--print",  # Non-interactive mode
            "--dangerously-skip-permissions",  # Skip permission prompts for automation
        ]

        # Claude CLI doesn't have --file flag, but we can enhance the prompt
        # with explicit file context information
        if file_paths:
            files_context = f"\n\nFiles to focus on: {', '.join(file_paths)}"
            prompt = prompt + files_context

        cmd.append(prompt)
        return cmd

    def _build_command_aider(
        self,
        prompt: str,
        repo_root: str,
        file_paths: list[str] | None = None,
    ) -> list[str]:
        """Build command for Aider CLI with secure argument handling.

        Args:
            prompt: The instruction prompt.
            repo_root: Repository root path.
            file_paths: List of file paths to add to aider's context for editing.
        """
        cmd = [
            self.config.bin_path,
            "--yes",  # Auto-accept changes
            "--no-auto-commits",  # Don't auto-commit (let user decide)
            "--no-git",  # Disable git operations (prevents hangs)
            "--no-pretty",  # Disable pretty output (prevents buffering issues)
            "--no-stream",  # Disable streaming (cleaner output)
            "--no-suggest-shell-commands",  # Don't suggest shell commands
            "--no-check-update",  # Don't check for updates
            "--model",
            f"openrouter/{self.config.model}",  # OpenRouter model
        ]

        # Add OpenRouter provider preferences if configured
        provider_order = os.environ.get("NINJA_OPENROUTER_PROVIDERS")
        if provider_order:
            # Create model settings file with provider preferences
            try:
                import yaml
            except ImportError:
                logger.warning("pyyaml not installed, provider preferences disabled")
            else:
                dirs = ensure_internal_dirs(repo_root)
                settings_file = safe_join(dirs["tasks"], "model_settings.yml")

                providers = [p.strip() for p in provider_order.split(",")]
                settings = [
                    {
                        "name": f"openrouter/{self.config.model}",
                        "extra_params": {
                            "provider": {
                                "order": providers,
                                "allow_fallbacks": False,
                            }
                        },
                    }
                ]

                with open(settings_file, "w") as f:
                    yaml.dump(settings, f)

                cmd.extend(["--model-settings-file", str(settings_file)])
                logger.info(f"Using OpenRouter provider order: {providers}")

        # IMPORTANT: Explicitly pass API key to override aider's cached key
        # Aider caches keys in ~/.aider*/oauth-keys.env and might use that instead
        # Use --api-key openrouter=KEY format (not --openai-api-key which doesn't work for OpenRouter)
        if not self.config.openai_api_key:
            raise ValueError(
                "No API key configured! Set OPENROUTER_API_KEY in ~/.ninja-mcp.env or environment. "
                "Without an API key, aider will hang waiting for interactive input."
            )
        cmd.extend(
            [
                "--api-key",
                f"openrouter={self.config.openai_api_key}",  # Force our OpenRouter key
            ]
        )

        # Add conservative limits to avoid incomplete responses
        # Timeout is configurable via NINJA_AIDER_TIMEOUT env var (default 300s = 5 minutes)
        aider_timeout = os.environ.get("NINJA_AIDER_TIMEOUT", "300")
        cmd.extend(
            [
                "--max-chat-history-tokens",
                "8000",  # Limit context to avoid token limits
                "--timeout",
                aider_timeout,  # API call timeout (configurable)
            ]
        )

        # Add file paths for aider to edit (critical for aider to know what to modify)
        if file_paths:
            for file_path in file_paths:
                # Check if path is a directory and skip it (aider doesn't support mixing dirs and files)
                path_obj = Path(file_path)
                if path_obj.is_dir():
                    logger.debug(
                        f"Skipping directory for aider --file: {file_path} (aider requires individual files only)"
                    )
                    continue
                # Use --file to add files to aider's context
                cmd.extend(["--file", file_path])

        # Note: No shlex.quote needed - subprocess with list args doesn't use shell
        cmd.extend(["--message", prompt])

        return cmd

    def _build_command_qwen(
        self,
        prompt: str,
        repo_root: str,
        file_paths: list[str] | None = None,
    ) -> list[str]:
        """Build command for Qwen Code CLI with secure argument handling.

        Args:
            prompt: The instruction prompt.
            repo_root: Repository root path (used for working directory context).
            file_paths: List of file paths to include in the prompt context.
        """
        # Qwen CLI doesn't have --file flag, enhance prompt with file context
        if file_paths:
            files_context = f"\n\nFiles to focus on: {', '.join(file_paths)}"
            prompt = prompt + files_context

        return [
            self.config.bin_path,
            "--non-interactive",
            "--message",
            prompt,
        ]

    def _build_command_generic(
        self,
        prompt: str,
        repo_root: str,
        file_paths: list[str] | None = None,
    ) -> list[str]:
        """Build command for generic/unknown CLI with secure argument handling.

        Args:
            prompt: The instruction prompt.
            repo_root: Repository root path (used for working directory context).
            file_paths: List of file paths to include in the prompt context.
        """
        # Generic CLI - enhance prompt with file context
        if file_paths:
            files_context = f"\n\nFiles to focus on: {', '.join(file_paths)}"
            prompt = prompt + files_context

        return [
            self.config.bin_path,
            prompt,
        ]

    def _build_command(self, task_file: Path, repo_root: str) -> list[str]:
        """
        Build the command to run AI Code CLI.

        .. deprecated::
            This method uses old CLI detection logic. New code should use
            self._strategy.build_command() instead. This method is kept for
            backwards compatibility with existing tests.

        Uses CLI adapter pattern to support different AI assistants.

        Args:
            task_file: Path to the task file.
            repo_root: Repository root path.

        Returns:
            Command as list of strings.
        """
        # Read the instruction to build a prompt
        with Path(task_file).open() as f:
            instruction = json.load(f)

        prompt = self._build_prompt_text(instruction, repo_root)

        # Extract file paths from instruction for CLI tools that need explicit file args
        file_scope = instruction.get("file_scope", {})
        context_paths = file_scope.get("context_paths", [])

        # Detect CLI type and build appropriate command
        cli_type = self._detect_cli_type()
        logger.debug(f"Detected CLI type: {cli_type}")
        logger.debug(f"Context paths for editing: {context_paths}")

        if cli_type == "aider":
            return self._build_command_aider(prompt, repo_root, file_paths=context_paths)
        elif cli_type == "qwen":
            return self._build_command_qwen(prompt, repo_root, file_paths=context_paths)
        elif cli_type == "claude":
            return self._build_command_claude(prompt, repo_root, file_paths=context_paths)
        elif cli_type == "gemini":
            return self._build_command_qwen(prompt, repo_root, file_paths=context_paths)
        else:
            return self._build_command_generic(prompt, repo_root, file_paths=context_paths)

    def _parse_output(self, stdout: str, stderr: str, exit_code: int) -> NinjaResult:
        """
        Parse Ninja Code CLI output to extract CONCISE results.

        .. deprecated::
            Use self._strategy.parse_output() instead. This method is kept for
            backwards compatibility with existing tests.

        IMPORTANT: This extracts only summary information, NOT source code.
        The orchestrator should receive minimal information about what changed.

        Args:
            stdout: Standard output.
            stderr: Standard error.
            exit_code: Process exit code.

        Returns:
            Parsed result with concise summary.
        """
        success = exit_code == 0
        combined_output = stdout + "\n" + stderr

        # ENHANCED: Detect aider-specific errors even with exit_code=0
        aider_error_patterns = [
            # Summarization failures (most common)
            r"summarization\s+failed",
            r"summarizer\s+.*?\s+failed",
            r"cannot\s+schedule\s+new\s+futures\s+after\s+shutdown",
            r"unexpectedly\s+failed\s+for\s+all\s+models",
            # Threading/async errors (often fatal but hidden)
            r"thread\s+.*?\s+error",
            r"event\s+loop\s+.*?\s+closed",
            r"event\s+loop\s+is\s+closed",
            # Model response errors
            r"incomplete\s+response",
            r"response\s+.*?\s+truncated",
            # File operation errors
            r"failed\s+to\s+(write|create|modify)",
            r"permission\s+denied.*?(writing|creating|modifying)",
            # Git errors (when --no-git might not work)
            r"git\s+.*?\s+error",
            r"repository\s+.*?\s+error",
        ]

        aider_error_detected = False
        aider_error_msg = ""

        for pattern in aider_error_patterns:
            match = re.search(pattern, combined_output, re.IGNORECASE)
            if match:
                aider_error_detected = True
                # Extract context around the error (80 chars before/after for context)
                start = max(0, match.start() - 80)
                end = min(len(combined_output), match.end() + 80)
                aider_error_msg = combined_output[start:end].strip()
                # Clean up extra whitespace
                aider_error_msg = " ".join(aider_error_msg.split())
                break

        # Override success if aider error detected
        if aider_error_detected:
            success = False
            logger.warning(
                f"Aider internal error detected despite exit_code={exit_code}: {aider_error_msg[:150]}"
            )

        # Extract file changes (what was modified)
        suspected_paths: list[str] = []
        file_patterns = [
            r"(?:wrote|created|modified|updated|edited)\s+['\"]?([^\s'\"]+)['\"]?",
            r"(?:writing|creating|modifying|updating|editing)\s+['\"]?([^\s'\"]+)['\"]?",
            r"file:\s*['\"]?([^\s'\"]+)['\"]?",
        ]
        for pattern in file_patterns:
            matches = re.findall(pattern, combined_output, re.IGNORECASE)
            for match in matches:
                if match and ("/" in match or "." in match):
                    suspected_paths.append(match)

        # Deduplicate paths
        suspected_paths = list(set(suspected_paths))

        # Build CONCISE summary (no code, just what happened)
        if success:
            if suspected_paths:
                file_count = len(suspected_paths)
                file_list = ", ".join(suspected_paths[:5])  # Max 5 files in summary
                if file_count > 5:
                    file_list += f" and {file_count - 5} more"
                summary = f"✅ Modified {file_count} file(s): {file_list}"
            else:
                summary = "✅ Task completed successfully"
        else:
            summary = "❌ Task failed"

        # Extract brief notes (error messages, warnings) - keep it SHORT
        notes = ""
        if not success:
            # Priority 1: Aider-specific errors
            if aider_error_detected:
                notes = f"🔧 Aider internal error: {aider_error_msg[:200]}"
                summary = "❌ Aider failed with internal error (retryable)"
            # Priority 2: Other errors from stderr
            elif stderr:
                # Extract just the error message, not full stack traces
                error_lines = [line.strip() for line in stderr.split("\n") if line.strip()]
                # Look for common error indicators
                for line in error_lines[-10:]:  # Last 10 lines only
                    lower = line.lower()
                    if any(
                        indicator in lower
                        for indicator in ["error:", "failed:", "exception:", "traceback"]
                    ):
                        notes = line[:200]  # Max 200 chars
                        break

                if not notes and error_lines:
                    notes = error_lines[-1][:200]  # Last line, max 200 chars

            # Detect specific OpenRouter/API errors
            if "finish_reason" in combined_output.lower():
                notes = "⚠️ Incomplete API response (token limit or timeout). Try smaller context or different model."

            # Detect invalid model ID errors
            if (
                "is not a valid model" in combined_output.lower()
                or "model not found" in combined_output.lower()
            ):
                model_match = re.search(
                    r"['\"]?([a-z]+/[a-z0-9._-]+)['\"]?\s+is not a valid",
                    combined_output,
                    re.IGNORECASE,
                )
                bad_model = model_match.group(1) if model_match else self.config.model
                fallbacks = ", ".join(FALLBACK_CODER_MODELS[:3])
                notes = f"❌ Invalid model ID: {bad_model}. Try: {fallbacks}"
                summary = f"❌ Model '{bad_model}' not found on OpenRouter"

            # Detect API key errors
            if "api key" in combined_output.lower() and (
                "not found" in combined_output.lower() or "invalid" in combined_output.lower()
            ):
                notes = "❌ OpenRouter API key missing or invalid. Set OPENROUTER_API_KEY in ~/.ninja-mcp.env"
                summary = "❌ API key error"

        # Try to extract structured summary if present (but keep it concise)
        try:
            json_match = re.search(r'\{[^{}]*"summary"[^{}]*\}', combined_output)
            if json_match:
                result_json = json.loads(json_match.group())
                extracted_summary = result_json.get("summary", "")
                if extracted_summary and len(extracted_summary) < 300:  # Only use if concise
                    summary = extracted_summary
        except (json.JSONDecodeError, AttributeError):
            pass

        return NinjaResult(
            success=success,
            summary=summary,
            notes=notes,
            suspected_touched_paths=suspected_paths,
            exit_code=exit_code,
            stdout=stdout,  # Full output saved to logs, not returned to orchestrator
            stderr=stderr,  # Full output saved to logs, not returned to orchestrator
            model_used=self.config.model,
            aider_error_detected=aider_error_detected,
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

            # Build prompt from instruction
            with Path(task_file).open() as f:
                instruction_data = json.load(f)

            prompt = self._build_prompt_text(instruction_data, repo_root)
            file_scope = instruction_data.get("file_scope", {})
            context_paths = file_scope.get("context_paths", [])

            # Build command using strategy
            cli_result = self._strategy.build_command(
                prompt=prompt,
                repo_root=repo_root,
                file_paths=context_paths,
                model=self.config.model,
            )

            # Log command without sensitive data (redact API key)
            safe_cmd = [
                arg if "api-key" not in prev.lower() else "***REDACTED***"
                for prev, arg in zip([""] + cli_result.command[:-1], cli_result.command)
            ]
            task_logger.info(f"Running {self._strategy.name}: {' '.join(safe_cmd)}")

            # Get timeout from strategy
            timeout = timeout_sec or self._strategy.get_timeout("quick")

            # Execute
            process = subprocess.run(
                cli_result.command,
                check=False,
                cwd=str(cli_result.working_dir),
                env=cli_result.env,
                stdin=subprocess.DEVNULL,  # Prevent stdin blocking
                capture_output=True,
                text=True,
                timeout=timeout,
            )

            task_logger.log_subprocess(
                cli_result.command, process.returncode, process.stdout, process.stderr
            )

            # Parse output using strategy
            parsed = self._strategy.parse_output(process.stdout, process.stderr, process.returncode)

            # Build result from parsed output
            result = NinjaResult(
                success=parsed.success,
                summary=parsed.summary,
                notes=parsed.notes,
                suspected_touched_paths=parsed.touched_paths,
                exit_code=process.returncode,
                stdout=process.stdout,
                stderr=process.stderr,
                model_used=self.config.model,
            )
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
                summary="⏱️ Task timed out",
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
                summary="❌ Ninja Code CLI not found",
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
                summary="❌ Execution error",
                notes=str(e)[:200],  # Keep error message concise
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
        task_type: str = "quick",
    ) -> NinjaResult:
        """
        Execute a task asynchronously.

        Args:
            repo_root: Repository root path.
            step_id: Step identifier.
            instruction: Instruction document.
            timeout_sec: Timeout in seconds.
            task_type: Type of task for model selection ('quick', 'sequential', 'parallel').

        Returns:
            Execution result.
        """
        task_logger = create_task_logger(repo_root, step_id)

        try:
            # Safety check with automatic enforcement (AUTO mode by default)
            task_desc = instruction.get("task", "")
            context_paths = instruction.get("file_scope", {}).get("context_paths", [])

            safety_results = validate_task_safety(
                repo_root=repo_root,
                task_description=task_desc,
                context_paths=context_paths,
            )

            # Log all warnings
            for warning in safety_results.get("warnings", []):
                task_logger.warning(warning)
                logger.warning(warning)

            # Log recommendations
            for rec in safety_results.get("recommendations", []):
                task_logger.info(f"💡 {rec}")

            # Log action taken
            action_taken = safety_results.get("action_taken")
            if action_taken == "auto_committed":
                logger.info("✅ Automatic safety commit created")

            # ENFORCE SAFETY: Refuse to run if safety check failed
            if not safety_results.get("safe", True):
                logs_path = task_logger.save()
                error_msg = "Safety check failed - refusing to run task"
                task_logger.error(error_msg)
                return NinjaResult(
                    success=False,
                    summary="❌ Safety check failed",
                    notes="\n".join(safety_results.get("warnings", [])),
                    raw_logs_path=logs_path,
                    exit_code=-2,
                    model_used=self.config.model,
                )

            # Store git info for recovery
            git_info = safety_results.get("git_info", {})
            if git_info.get("safety_tag"):
                recovery_cmd = f"git reset --hard {git_info['safety_tag']}"
                task_logger.info(f"🔖 Recovery point: {recovery_cmd}")
                logger.info(f"🔖 Recovery point: {recovery_cmd}")

            # Write task file
            task_file = self._write_task_file(repo_root, step_id, instruction)
            task_logger.info(f"Wrote task file: {task_file}")

            # Select model intelligently based on task type
            model, use_coding_plan = self._select_model_for_task(instruction, task_type)

            task_logger.info(f"Starting async task execution with model: {model}")
            task_logger.set_metadata("instruction", instruction)
            task_logger.set_metadata("model", model)
            task_logger.set_metadata("task_type", task_type)

            # Build prompt from instruction
            with Path(task_file).open() as f:
                instruction_data = json.load(f)

            prompt = self._build_prompt_text(instruction_data, repo_root)
            file_scope = instruction_data.get("file_scope", {})
            context_paths = file_scope.get("context_paths", [])

            # Check if strategy supports dialogue mode and task type is sequential
            use_dialogue_mode = (
                self._strategy.capabilities.supports_dialogue_mode and task_type == "sequential"
            )

            if use_dialogue_mode:
                task_logger.info("Using dialogue mode for sequential execution")
            else:
                task_logger.info("Using atomic mode (subprocess per step)")

            # Build command using strategy
            additional_flags = {"use_coding_plan": use_coding_plan} if use_coding_plan else None

            cli_result = self._strategy.build_command(
                prompt=prompt,
                repo_root=repo_root,
                file_paths=context_paths,
                model=model,
                additional_flags=additional_flags,
            )

            # Log command (redact sensitive data)
            safe_cmd = [
                arg if "api-key" not in prev.lower() else "***REDACTED***"
                for prev, arg in zip([""] + cli_result.command[:-1], cli_result.command)
            ]
            task_logger.info(f"Running {self._strategy.name}: {' '.join(safe_cmd)}")

            # Get timeout from strategy
            timeout = timeout_sec or self._strategy.get_timeout(task_type)

            # Execute asynchronously using strategy-built command
            process = await asyncio.create_subprocess_exec(
                *cli_result.command,
                cwd=str(cli_result.working_dir),
                env=cli_result.env,
                stdin=asyncio.subprocess.DEVNULL,  # Prevent stdin blocking
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

            except TimeoutError:
                process.kill()
                await process.wait()
                task_logger.error(f"Task timed out after {timeout}s")
                logs_path = task_logger.save()
                return NinjaResult(
                    success=False,
                    summary="⏱️ Task timed out",
                    notes=f"Execution exceeded {timeout}s timeout",
                    raw_logs_path=logs_path,
                    exit_code=-1,
                    model_used=model,
                )

            task_logger.log_subprocess(cli_result.command, exit_code, stdout, stderr)

            # Parse output using strategy
            parsed = self._strategy.parse_output(stdout, stderr, exit_code)

            # Build result from parsed output
            result = NinjaResult(
                success=parsed.success,
                summary=parsed.summary,
                notes=parsed.notes,
                suspected_touched_paths=parsed.touched_paths,
                raw_logs_path=task_logger.save(),
                exit_code=exit_code,
                stdout=stdout,
                stderr=stderr,
                model_used=model,
                aider_error_detected=parsed.retryable_error,  # Generic retryable error flag
            )

            task_logger.info(
                f"Task {'succeeded' if result.success else 'failed'}: {result.summary}"
            )

            return result

        except FileNotFoundError:
            task_logger.error(f"Ninja Code CLI not found: {self.config.bin_path}")
            logs_path = task_logger.save()
            # Use locals() to check if model was defined before error
            model_used = locals().get("model", self.config.model)
            return NinjaResult(
                success=False,
                summary="❌ Ninja Code CLI not found",
                notes=f"Could not find executable: {self.config.bin_path}. "
                f"Install Ninja Code CLI or set NINJA_CODE_BIN environment variable.",
                raw_logs_path=logs_path,
                exit_code=-1,
                model_used=model_used,
            )
        except Exception as e:
            task_logger.error(f"Unexpected error: {e}")
            logs_path = task_logger.save()
            # Use locals() to check if model was defined before error
            model_used = locals().get("model", self.config.model)
            return NinjaResult(
                success=False,
                summary="❌ Execution error",
                notes=str(e)[:200],  # Keep error message concise
                raw_logs_path=logs_path,
                exit_code=-1,
                model_used=model_used,
            )

    async def execute_with_session(
        self,
        task: str,
        repo_root: str,
        step_id: str,
        session_id: str | None = None,
        create_session: bool = False,
        context_paths: list[str] | None = None,
        allowed_globs: list[str] | None = None,
        deny_globs: list[str] | None = None,
        timeout_sec: int | None = None,
        task_type: str = "quick",
    ) -> NinjaResult:
        """Execute task with session management.

        Args:
            task: Task description.
            repo_root: Repository root path.
            step_id: Step identifier.
            session_id: Optional session ID to continue.
            create_session: If True, create new session for conversation.
            context_paths: Files to include in context.
            allowed_globs: Allowed file patterns.
            deny_globs: Denied file patterns.
            timeout_sec: Timeout in seconds.
            task_type: Type of task ('quick', 'sequential', 'parallel').

        Returns:
            NinjaResult with session_id if session was used.
        """
        # Load or create session
        session = None
        if session_id:
            session = self.session_manager.load_session(session_id)
            if not session:
                return NinjaResult(
                    success=False,
                    summary=f"❌ Session {session_id} not found",
                    notes="Session may have been deleted or expired",
                    model_used=self.config.model,
                )
        elif create_session:
            session = self.session_manager.create_session(
                repo_root=repo_root,
                model=self.config.model,
                metadata={"context_paths": context_paths or []},
            )

        # Add user message to session
        if session:
            session.add_message("user", task)
            self.session_manager.save_session(session)
            logger.info(f"📝 Added user message to session {session.session_id}")

        # Build instruction
        builder = InstructionBuilder(repo_root, mode=ExecutionMode.QUICK)
        instruction = builder.build_quick_task(
            task=task,
            context_paths=context_paths or [],
            allowed_globs=allowed_globs or ["**/*"],
            deny_globs=deny_globs or [],
        )

        # Execute task
        result = await self.execute_async(
            repo_root=repo_root,
            step_id=step_id,
            instruction=instruction,
            timeout_sec=timeout_sec,
            task_type=task_type,
        )

        # Add assistant response to session
        if session:
            session.add_message(
                "assistant",
                result.summary,
                metadata={
                    "touched_paths": result.suspected_touched_paths,
                    "success": result.success,
                    "model": result.model_used,
                },
            )
            self.session_manager.save_session(session)
            result.session_id = session.session_id
            logger.info(f"💾 Saved assistant response to session {session.session_id}")

        return result


# Backwards compatibility aliases
QwenConfig = NinjaConfig
QwenResult = NinjaResult
QwenDriver = NinjaDriver
