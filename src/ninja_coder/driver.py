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
import shutil
import signal
import subprocess
import tempfile
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ninja_coder.model_selector import ModelSelector
from ninja_coder.models import (
    ExecutionMode,
    PlanStep,
    TaskComplexity,
)
from ninja_coder.safety import validate_task_safety
from ninja_coder.sessions import SessionManager
from ninja_coder.strategies import CLIStrategyRegistry
from ninja_coder.worktree import WorktreeInfo, WorktreeManager
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

try:
    import psutil  # noqa: F401
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False


#: Buffer limit for subprocess stdout/stderr pipes. The asyncio default
#: (64 KiB) is too small: opencode `--format json` can emit single JSON
#: lines larger than that, which crashes the reader with
#: "Separator is found, but chunk is longer than limit".
SUBPROCESS_STREAM_LIMIT = 16 * 1024 * 1024  # 16 MiB

#: Default inactivity-watchdog thresholds (seconds) per task type.
_INACTIVITY_TIMEOUT_DEFAULTS: dict[str, float] = {
    "quick": 60.0,
    "sequential": 120.0,
    "parallel": 120.0,
}


def _get_inactivity_timeout(task_type: str, model: str = "") -> float:
    """Resolve the inactivity-watchdog threshold for a task type.

    ``NINJA_INACTIVITY_TIMEOUT``, when set, overrides every task type.
    Otherwise per-type defaults apply (quick=60s, sequential/parallel=120s).

    Models that delegate work to nested sub-agents (e.g. ``gpt-5.6-luna``)
    legitimately go silent while a child agent runs, so they get a relaxed
    threshold via ``NINJA_INACTIVITY_TIMEOUT_AGENT_MODELS`` (default 180s).

    Args:
        task_type: Type of task ('quick', 'sequential', 'parallel'); the
            '*_plan' variants inherit their base type's default.
        model: Resolved model name; used to pick a relaxed threshold for
            agent-spawning models.

    Returns:
        Inactivity timeout in seconds.
    """
    override = os.environ.get("NINJA_INACTIVITY_TIMEOUT")
    if override is not None:
        return float(override)

    agent_models = os.environ.get("NINJA_INACTIVITY_TIMEOUT_AGENT_MODELS", "180")
    try:
        agent_timeout = float(agent_models)
    except ValueError:
        agent_timeout = 180.0

    model_lower = model.lower()
    if "zai-coding-plan" in model_lower or "coding-plan" in model_lower:
        # Coding-plan models spend long stretches "thinking" server-side with
        # no local CPU activity; give them a much more generous window.
        coding_plan_timeout = os.environ.get("NINJA_INACTIVITY_TIMEOUT_CODING_PLAN", "300")
        try:
            return float(coding_plan_timeout)
        except ValueError:
            return 300.0

    if model_lower and any(
        tag in model_lower for tag in ("luna", "grok", "agent")
    ):
        return agent_timeout

    base_type = task_type.removesuffix("_plan")
    return _INACTIVITY_TIMEOUT_DEFAULTS.get(base_type, _INACTIVITY_TIMEOUT_DEFAULTS["quick"])


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
        """Create config from environment variables with auto-detection fallback."""
        api_key = os.environ.get("OPENROUTER_API_KEY") or os.environ.get("OPENAI_API_KEY", "")

        # Model priority: NINJA_CODER_MODEL > NINJA_MODEL > OPENROUTER_MODEL > OPENAI_MODEL > default
        model = (
            os.environ.get("NINJA_CODER_MODEL")
            or os.environ.get("NINJA_MODEL")
            or os.environ.get("OPENROUTER_MODEL")
            or os.environ.get("OPENAI_MODEL")
            or DEFAULT_CODER_MODEL
        )

        # Binary path with auto-detection fallback
        bin_path = os.environ.get("NINJA_CODE_BIN", DEFAULT_CODE_BIN)

        # If configured path doesn't exist, try to auto-detect using which
        if not Path(bin_path).exists():
            # Extract binary name (handle both full paths and binary names)
            bin_name = Path(bin_path).name if "/" in bin_path else bin_path
            detected_path = shutil.which(bin_name)

            if detected_path:
                logger.info(
                    f"Configured binary path '{bin_path}' not found. Auto-detected: {detected_path}"
                )
                bin_path = detected_path
            elif bin_name != DEFAULT_CODE_BIN:
                # Try fallback to default binary
                default_path = shutil.which(DEFAULT_CODE_BIN)
                if default_path:
                    logger.warning(
                        f"Configured binary '{bin_name}' not found. "
                        f"Falling back to default: {default_path}"
                    )
                    bin_path = default_path

        return cls(
            bin_path=bin_path,
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
    worktree_branch: str | None = None  # Feature branch when worktree isolation was used
    worktree_path: str | None = None  # Detached worktree path when isolation was used


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
        self._selector_cache: ModelSelector | None = None

        # Get strategy based on binary path
        self._strategy = CLIStrategyRegistry.get_strategy(self.config.bin_path, self.config)

        # Initialize session manager
        from ninja_common.path_utils import get_cache_dir

        cache_dir = get_cache_dir()
        self.session_manager = SessionManager(cache_dir)

        # Initialize structured logger
        from ninja_common.structured_logger import StructuredLogger

        log_dir = cache_dir / "logs"
        self.structured_logger = StructuredLogger("ninja-coder", log_dir)

        logger.info(f"Initialized NinjaDriver with {self._strategy.name} strategy")
        self.structured_logger.info(
            "Driver initialized",
            cli_name=self._strategy.name,
            model=self.config.model,
        )

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
        # Explicit model class override (smart/balanced/fast) wins over routing
        model_class = instruction.get("model_class")
        if model_class:
            recommendation = self._model_selector().select_by_class(model_class)
            logger.info(
                f"Selected model by class '{model_class}': {recommendation.model} "
                f"(reason: {recommendation.reason})"
            )
            return recommendation.model, recommendation.use_coding_plan_api

        # Determine task complexity (normalize *_plan suffixes to base types)
        base_type = task_type.removesuffix("_plan")
        if base_type == "parallel":
            complexity = TaskComplexity.PARALLEL
            fanout = instruction.get("parallel_context", {}).get("total_steps", 1)
        elif base_type == "sequential":
            complexity = TaskComplexity.SEQUENTIAL
            fanout = 1
        else:
            complexity = TaskComplexity.QUICK
            fanout = 1

        # Select model using model selector directly
        recommendation = self._model_selector().select_model(
            complexity,
            fanout=fanout,
        )

        logger.info(
            f"Selected model: {recommendation.model} "
            f"(reason: {recommendation.reason}, "
            f"estimated cost: {recommendation.cost_estimate})"
        )

        return recommendation.model, recommendation.use_coding_plan_api

    def _model_selector(self) -> ModelSelector:
        """Return a configured ModelSelector (cached on the instance)."""
        if self._selector_cache is None:
            self._selector_cache = ModelSelector(default_model=self.config.model)
        return self._selector_cache

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
            self.config.model,  # Model (provider prefix included)
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
                        "name": self.config.model,
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
                for prev, arg in zip(["", *cli_result.command[:-1]], cli_result.command)
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
            parsed = self._strategy.parse_output(
                process.stdout, process.stderr, process.returncode, repo_root=repo_root
            )

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

    async def _stream_with_activity_timeout(
        self,
        process: asyncio.subprocess.Process,
        max_timeout: float,
        inactivity_timeout: float = 60.0,
        cpu_check_threshold: float = 1.0,
    ) -> tuple[str, str]:
        """Stream subprocess stdout with activity-based timeout extension.

        Instead of a single wall-clock timeout, monitors output activity.
        When no output arrives for inactivity_timeout seconds, checks CPU usage:
        - CPU still active → process is computing, extend inactivity timer
        - CPU idle → process is stuck, raise TimeoutError early
        Absolute max_timeout still applies as a hard ceiling.
        """
        import time as _time

        stdout_chunks: list[bytes] = []
        absolute_deadline = _time.monotonic() + max_timeout
        last_activity = _time.monotonic()

        async def _read_stderr() -> bytes:
            if process.stderr:
                return await process.stderr.read()
            return b""

        stderr_task = asyncio.create_task(_read_stderr())

        assert process.stdout is not None

        try:
            while True:
                now = _time.monotonic()

                if now >= absolute_deadline:
                    raise TimeoutError(f"Absolute timeout of {max_timeout:.0f}s exceeded")

                seconds_idle = now - last_activity
                remaining_inactivity = inactivity_timeout - seconds_idle

                if remaining_inactivity <= 0:
                    # No output for a while — inspect process tree
                    cpu_active = False
                    if PSUTIL_AVAILABLE and process.pid:
                        try:
                            import psutil as _psutil

                            proc = _psutil.Process(process.pid)

                            # Check parent CPU
                            parent_cpu = proc.cpu_percent(interval=0.5)

                            # Check children CPU — find stuck ones (high CPU, no relation to output)
                            try:
                                children = proc.children(recursive=True)
                            except _psutil.NoSuchProcess:
                                children = []

                            stuck_children: list[_psutil.Process] = []
                            active_children: list[_psutil.Process] = []
                            for child in children:
                                try:
                                    child_cpu = child.cpu_percent(interval=0.2)
                                    cmdline = " ".join(child.cmdline())
                                    if child_cpu > 50.0:  # pegging CPU
                                        if any(
                                            s in cmdline
                                            for s in ["pyright", "langserver", "tsserver"]
                                        ):
                                            stuck_children.append(child)
                                            logger.warning(
                                                f"[watchdog] Detected stuck LSP child pid={child.pid} "
                                                f"cpu={child_cpu:.0f}% cmd={cmdline[:80]!r}"
                                            )
                                        else:
                                            active_children.append(child)
                                except (_psutil.NoSuchProcess, _psutil.AccessDenied):
                                    pass

                            # Kill stuck LSP children — let OpenCode recover
                            for child in stuck_children:
                                try:
                                    child.kill()
                                    logger.warning(
                                        f"[watchdog] Killed stuck LSP child pid={child.pid}"
                                    )
                                except Exception as ke:
                                    logger.debug(
                                        f"[watchdog] Could not kill child {child.pid}: {ke}"
                                    )

                            if parent_cpu > cpu_check_threshold or active_children:
                                cpu_active = True
                                logger.info(
                                    f"[activity] No output for {seconds_idle:.0f}s but "
                                    f"parent_cpu={parent_cpu:.1f}% active_children={len(active_children)} — extending"
                                )
                            elif stuck_children:
                                # Killed stuck children, give OpenCode a chance to recover
                                cpu_active = True
                                logger.info(
                                    f"[watchdog] Killed {len(stuck_children)} stuck LSP child(ren), "
                                    f"giving OpenCode 30s to recover"
                                )
                                last_activity = _time.monotonic()
                                # Shrink inactivity window for this recovery attempt
                                inactivity_timeout = min(inactivity_timeout, 30.0)

                        except Exception as e:
                            logger.debug(f"[watchdog] Process inspection failed: {e}")

                    if cpu_active:
                        last_activity = _time.monotonic()
                        continue
                    else:
                        raise TimeoutError(
                            f"Process inactive for {seconds_idle:.0f}s with no CPU activity"
                        )

                read_timeout = min(remaining_inactivity, absolute_deadline - now, 5.0)

                try:
                    line = await asyncio.wait_for(
                        process.stdout.readline(),
                        timeout=read_timeout,
                    )
                except TimeoutError:
                    continue  # Re-evaluate activity on next loop iteration

                if line:
                    stdout_chunks.append(line)
                    last_activity = _time.monotonic()
                else:
                    break  # EOF — process finished writing

        finally:
            stderr_task.cancel()
            try:
                stderr_bytes = await asyncio.wait_for(stderr_task, timeout=5.0)
            except (TimeoutError, asyncio.CancelledError):
                stderr_bytes = b""

        await process.wait()

        stdout = b"".join(stdout_chunks).decode(errors="replace")
        stderr = stderr_bytes.decode(errors="replace")
        return stdout, stderr

    @staticmethod
    def _attach_worktree_info(
        result: NinjaResult, worktree_info: WorktreeInfo | None
    ) -> NinjaResult:
        """Attach worktree isolation details to an execution result.

        Sets the worktree_branch/worktree_path fields and appends a one-line
        merge hint to the result notes so callers can review and merge the
        isolated changes. No-op when no worktree was created.

        Args:
            result: Execution result to enrich.
            worktree_info: Worktree details, or None when isolation was not used.

        Returns:
            The same result object, enriched when a worktree was used.
        """
        if worktree_info is None:
            return result
        result.worktree_branch = worktree_info.branch
        result.worktree_path = str(worktree_info.path)
        hint = (
            f"🔀 Worktree isolation: changes on branch '{worktree_info.branch}' "
            f"at {worktree_info.path}. Review/merge: git merge {worktree_info.branch}"
        )
        result.notes = f"{result.notes}\n{hint}" if result.notes else hint
        return result

    @staticmethod
    def _remap_context_paths(
        instruction: dict[str, Any],
        original_root: str,
        worktree_root: str,
    ) -> dict[str, Any]:
        """Remap absolute context paths from the original repo into a worktree.

        When worktree isolation is active the agent runs inside the worktree,
        so context paths must point at the worktree copy of the files. Paths
        that are relative or already inside the worktree are left untouched.

        Args:
            instruction: Instruction document to mutate.
            original_root: Path of the main repository.
            worktree_root: Path of the isolation worktree.

        Returns:
            The instruction document with remapped context paths.
        """
        file_scope = instruction.get("file_scope", {})
        context_paths = file_scope.get("context_paths", [])
        result_instruction = instruction

        if context_paths:
            original = Path(original_root).resolve()
            # NOTE: the worktree spelling is preserved verbatim (no resolve()):
            # the prompt must contain the exact execution_dir/cwd string, not
            # its canonicalized twin (/tmp vs /private/tmp on macOS).
            worktree_base = Path(worktree_root)
            # Raw spellings for a string-prefix fallback (covers paths that
            # do not exist on disk and /tmp vs /private/tmp canonicalization
            # mismatches where resolve() cannot align them).
            raw_spellings = [
                s for s in (original_root.rstrip(os.sep), str(original).rstrip(os.sep)) if s
            ]
            remapped: list[str] = []
            for path in context_paths:
                p = Path(path)
                if not p.is_absolute():
                    remapped.append(path)
                    continue
                try:
                    rel = p.resolve().relative_to(original)
                except ValueError:
                    rel = None
                if rel is not None:
                    remapped.append(str(worktree_base / rel))
                    continue
                # Fallback: exact prefix match on path boundaries.
                replaced = False
                for spelling in sorted(raw_spellings, key=len, reverse=True):
                    if path == spelling or path.startswith(spelling + os.sep):
                        remapped.append(worktree_root.rstrip(os.sep) + path[len(spelling) :])
                        replaced = True
                        break
                if not replaced:
                    remapped.append(path)

            file_scope = {**file_scope, "context_paths": remapped}
            result_instruction = {**result_instruction, "file_scope": file_scope}

        # Test commands may embed absolute main-repo paths
        # (e.g. `pytest /tmp/main/tests/...`). Rewrite those as text so the
        # agent runs them against the worktree copy.
        test_plan = result_instruction.get("test_plan")
        if isinstance(test_plan, dict) and test_plan:
            new_plan: dict[str, Any] = {}
            changed = False
            for key, value in test_plan.items():
                if isinstance(value, list):
                    new_items = [
                        NinjaDriver._rewrite_path_in_text(str(v), original_root, worktree_root)
                        if isinstance(v, str)
                        else v
                        for v in value
                    ]
                    changed = changed or new_items != value
                    new_plan[key] = new_items
                elif isinstance(value, str):
                    new_value = NinjaDriver._rewrite_path_in_text(
                        value, original_root, worktree_root
                    )
                    changed = changed or new_value != value
                    new_plan[key] = new_value
                else:
                    new_plan[key] = value
            if changed:
                result_instruction = {**result_instruction, "test_plan": new_plan}

        return result_instruction

    @staticmethod
    def _rewrite_path_in_text(text: str, original_root: str, worktree_root: str) -> str:
        """Rewrite absolute main-repo paths to the worktree in free text.

        Exact path-boundary replacement (not a blind substring replace): the
        match must end at a path boundary (``/``, whitespace, quote, backtick,
        colon, newline or end of string). Both the raw ``original_root``
        spelling and its canonically resolved form (``Path.resolve()``, e.g.
        ``/tmp`` vs ``/private/tmp`` on macOS) are rewritten, so
        cwd-canonicalization differences cannot leak the main-repo path into
        the prompt.

        Args:
            text: Free-form text (prompt, task, instructions, test command).
            original_root: Path of the main repository.
            worktree_root: Path of the isolation worktree.

        Returns:
            Text with main-repo paths replaced by the worktree path.
        """
        if not text or not original_root or not worktree_root:
            return text
        spellings: list[str] = []
        for candidate in (original_root, str(Path(original_root).resolve())):
            normalized = candidate.rstrip(os.sep) or candidate
            if normalized and normalized not in spellings:
                spellings.append(normalized)
        # Longest first so the resolved spelling wins when nested.
        spellings.sort(key=len, reverse=True)
        result = text
        for spelling in spellings:
            if spelling == worktree_root.rstrip(os.sep):
                continue
            pattern = re.compile(rf"{re.escape(spelling)}(?=[/\s'\"`:,\n]|$)")
            result = pattern.sub(worktree_root.rstrip(os.sep), result)
        return result

    @staticmethod
    def _remap_instruction_text_roots(
        instruction: dict[str, Any],
        original_root: str,
        worktree_root: str,
    ) -> dict[str, Any]:
        """Point embedded main-repo paths in instruction text at the worktree.

        ``execute_async`` creates the worktree *after* ``tools.py`` bakes the
        plan prompt (``PromptBuilder`` embeds ``- **Repository**: <main>`` and
        absolute context paths into ``task``/``instructions``). Updating only
        the ``repo_root`` key leaves those baked strings pointing at the main
        repo, and the model then writes files outside the worktree. This
        rewrites the free-text fields (``task``, ``instructions``,
        ``step.task``) with exact path-boundary matching.

        Args:
            instruction: Instruction document to sanitize.
            original_root: Path of the main repository.
            worktree_root: Path of the isolation worktree.

        Returns:
            The instruction document with text roots remapped.
        """
        instruction = dict(instruction)
        for key in ("task", "instructions"):
            value = instruction.get(key)
            if isinstance(value, str) and value:
                instruction[key] = NinjaDriver._rewrite_path_in_text(
                    value, original_root, worktree_root
                )
        step = instruction.get("step")
        if isinstance(step, dict) and isinstance(step.get("task"), str):
            instruction["step"] = {
                **step,
                "task": NinjaDriver._rewrite_path_in_text(
                    step["task"], original_root, worktree_root
                ),
            }
        return instruction

    async def execute_async(
        self,
        repo_root: str,
        step_id: str,
        instruction: dict[str, Any],
        timeout_sec: int | None = None,
        task_type: str = "quick",
        session_id: str | None = None,
    ) -> NinjaResult:
        """
        Execute a task asynchronously.

        Args:
            repo_root: Repository root path.
            step_id: Step identifier.
            instruction: Instruction document.
            timeout_sec: Timeout in seconds.
            task_type: Type of task for model selection ('quick', 'sequential', 'parallel').
            session_id: Optional session ID for logging.

        Returns:
            Execution result.
        """
        task_logger = create_task_logger(repo_root, step_id)
        worktree_info: WorktreeInfo | None = None

        try:
            # Safety check with automatic enforcement (AUTO mode by default)
            task_desc = instruction.get("task", "")
            context_paths = instruction.get("file_scope", {}).get("context_paths", [])

            # OpenCode serve-pool mode uses a long-running server rooted at
            # repo_root, so worktree isolation does not apply there.
            serve_pool_mode = (
                os.environ.get("NINJA_OPENCODE_SERVE_MODE") == "1"
                and self._strategy.name == "opencode"
            )

            # Worktree isolation: only long sequential/parallel plans run in a
            # detached git worktree; quick/simple tasks run in-place with the
            # legacy AUTO safety-commit (per-type policy, see worktree.py).
            if not serve_pool_mode and WorktreeManager.is_enabled(task_type):
                worktree_info = WorktreeManager().create(
                    repo_root=repo_root,
                    task_hint=task_desc,
                    step_id=step_id,
                    task_type=task_type,
                )
            execution_dir = str(worktree_info.path) if worktree_info else repo_root
            if worktree_info:
                task_logger.info(
                    f"🔀 Worktree isolation: branch '{worktree_info.branch}' "
                    f"at {worktree_info.path}"
                )
                # The instruction travels with the task; point it at the worktree.
                instruction = {**instruction, "repo_root": execution_dir}
                # Remap context paths from the original repo into the worktree so
                # the agent focuses on files that actually exist in the execution
                # directory instead of absolute paths pointing at the main repo.
                instruction = self._remap_context_paths(
                    instruction, repo_root, execution_dir
                )
                # The plan prompt text (baked by PromptBuilder in tools.py before
                # the worktree existed) embeds `- **Repository**: <main>` and
                # absolute main-repo paths. Rewrite those to the worktree so the
                # model writes files inside the isolation worktree, not main.
                instruction = self._remap_instruction_text_roots(
                    instruction, repo_root, execution_dir
                )
                context_paths = instruction.get("file_scope", {}).get("context_paths", [])

            safety_results = validate_task_safety(
                repo_root=repo_root,
                task_description=task_desc,
                context_paths=context_paths,
                skip_auto_commit=worktree_info is not None,
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
                return self._attach_worktree_info(
                    NinjaResult(
                        success=False,
                        summary="❌ Safety check failed",
                        notes="\n".join(safety_results.get("warnings", [])),
                        raw_logs_path=logs_path,
                        exit_code=-2,
                        model_used=self.config.model,
                    ),
                    worktree_info,
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

            # Structured logging: Task start
            self.structured_logger.info(
                f"Starting task execution: {task_desc[:100]}...",
                session_id=session_id,
                task_id=step_id,
                cli_name=self._strategy.name,
                model=model,
                task_type=task_type,
                repo_root=repo_root,
                context_file_count=len(context_paths),
            )

            # Build prompt from instruction
            with Path(task_file).open() as f:
                instruction_data = json.load(f)

            prompt = self._build_prompt_text(instruction_data, execution_dir)
            if worktree_info is not None:
                # Belt-and-braces: any main-repo path that survived the
                # instruction rewrite (e.g. baked plan-prompt text) must not
                # reach the model — it writes files wherever the prompt points.
                prompt = self._rewrite_path_in_text(prompt, repo_root, execution_dir)
            file_scope = instruction_data.get("file_scope", {})
            context_paths = file_scope.get("context_paths", [])

            # Check if multi-agent orchestration is needed
            # Never auto-enable for sequential/parallel steps — they are always atomic
            enable_multi_agent = False
            if hasattr(self._strategy, "build_command_with_multi_agent") and task_type not in (
                "sequential",
                "parallel",
                "sequential_plan",
                "parallel_plan",
            ):
                # Import multi-agent orchestrator
                from ninja_coder.multi_agent import MultiAgentOrchestrator

                orchestrator = MultiAgentOrchestrator(self._strategy)
                # Analyze only the raw task, not the full system prompt with agent descriptions
                raw_task = instruction_data.get("task", prompt)
                analysis = orchestrator.analyze_task(raw_task, context_paths)

                if orchestrator.should_use_multi_agent(analysis):
                    enable_multi_agent = True
                    agents = orchestrator.select_agents(prompt, analysis)
                    task_logger.info(
                        f"🤖 Multi-agent mode activated with {len(agents)} agents: "
                        f"{', '.join(agents)}"
                    )
                    task_logger.set_metadata("multi_agent", True)
                    task_logger.set_metadata("agents", agents)

                    # Structured logging: Multi-agent activation
                    self.structured_logger.log_multi_agent(
                        agents=agents,
                        task_id=step_id,
                        session_id=session_id,
                        cli_name=self._strategy.name,
                        complexity=analysis.complexity,
                        task_type=analysis.task_type,
                    )

            # --- OpenCode serve pool path ---
            # When NINJA_OPENCODE_SERVE_MODE=1 and strategy is opencode,
            # use the long-running server pool instead of spawning a subprocess.
            # (Worktree isolation is disabled in this mode — see above.)
            if serve_pool_mode:
                from ninja_coder.strategies.opencode_server_pool import get_pool

                pool = get_pool(bin_path=self.config.bin_path)
                task_logger.info("[serve-pool] Using opencode serve pool")

                try:
                    pool_result = await pool.execute(
                        repo_root=repo_root,
                        prompt=prompt,
                        model=model,
                        timeout=timeout_sec or self._strategy.get_timeout(task_type),
                    )
                except Exception as pool_exc:
                    task_logger.error(f"[serve-pool] Execution failed: {pool_exc}")
                    logs_path = task_logger.save()
                    return NinjaResult(
                        success=False,
                        summary=f"❌ Serve pool error: {pool_exc}",
                        raw_logs_path=logs_path,
                        model_used=model,
                    )

                result = NinjaResult(
                    success=pool_result.success,
                    summary=f"✅ {pool_result.summary}"
                    if pool_result.success
                    else f"❌ {pool_result.summary}",
                    suspected_touched_paths=pool_result.files_changed,
                    raw_logs_path=task_logger.save(),
                    model_used=model,
                    session_id=pool_result.session_id,
                )
                self.structured_logger.log_result(
                    success=result.success,
                    summary=result.summary,
                    session_id=session_id,
                    task_id=step_id,
                    cli_name=self._strategy.name,
                    model=model,
                    touched_paths=result.suspected_touched_paths,
                    exit_code=0,
                )
                return result
            # --- end serve pool path ---

            # Check if strategy supports dialogue mode and task type is sequential
            use_dialogue_mode = (
                self._strategy.capabilities.supports_dialogue_mode and task_type == "sequential"
            )

            if use_dialogue_mode:
                task_logger.info("Using dialogue mode for sequential execution")
            else:
                task_logger.info("Using atomic mode (subprocess per step)")

            # Build command using strategy
            if enable_multi_agent:
                # Use multi-agent command builder
                context = {
                    "complexity": analysis.complexity,
                    "task_type": analysis.task_type,
                    "estimated_files": analysis.estimated_files,
                }
                cli_result = self._strategy.build_command_with_multi_agent(
                    prompt=prompt,
                    repo_root=execution_dir,
                    agents=agents,
                    context=context,
                    file_paths=context_paths,
                    model=model,
                )
            else:
                # Use standard command builder
                additional_flags = {"use_coding_plan": use_coding_plan} if use_coding_plan else None

                cli_result = self._strategy.build_command(
                    prompt=prompt,
                    repo_root=execution_dir,
                    file_paths=context_paths,
                    model=model,
                    additional_flags=additional_flags,
                )

            # Log command (redact sensitive data)
            safe_cmd = [
                arg if "api-key" not in prev.lower() else "***REDACTED***"
                for prev, arg in zip(["", *cli_result.command[:-1]], cli_result.command)
            ]
            task_logger.info(f"Running {self._strategy.name}: {' '.join(safe_cmd)}")

            # Structured logging: Command execution
            self.structured_logger.log_command(
                command=cli_result.command,
                session_id=session_id,
                task_id=step_id,
                cli_name=self._strategy.name,
                model=model,
                working_dir=str(cli_result.working_dir),
            )

            # Get timeout from strategy
            max_timeout = timeout_sec or self._strategy.get_timeout(task_type)

            # Execute asynchronously using strategy-built command
            process = await asyncio.create_subprocess_exec(
                *cli_result.command,
                cwd=str(cli_result.working_dir),
                env=cli_result.env,
                stdin=asyncio.subprocess.DEVNULL,  # Prevent stdin blocking
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                limit=SUBPROCESS_STREAM_LIMIT,  # JSON lines can exceed the 64 KiB default
                start_new_session=True,  # Own process group — ensures children (pyright etc.) die with parent
            )

            try:
                start_time = asyncio.get_event_loop().time()
                inactivity_timeout = _get_inactivity_timeout(task_type, model=model)

                task_logger.debug(
                    f"Starting subprocess with {max_timeout}s timeout, "
                    f"{inactivity_timeout}s inactivity threshold"
                )

                stdout, stderr = await self._stream_with_activity_timeout(
                    process,
                    max_timeout=float(max_timeout),
                    inactivity_timeout=inactivity_timeout,
                )
                exit_code = process.returncode or 0

                total_time = asyncio.get_event_loop().time() - start_time
                task_logger.info(f"Task completed in {total_time:.1f}s")

            except TimeoutError as e:
                task_logger.warning(f"Task timed out after {max_timeout}s, killing process group")
                try:
                    if process.pid:
                        os.killpg(os.getpgid(process.pid), signal.SIGTERM)
                except (ProcessLookupError, PermissionError):
                    process.kill()  # fallback
                try:
                    await asyncio.wait_for(process.wait(), timeout=5)
                except TimeoutError:
                    task_logger.error("Process group did not die after SIGTERM, forcing SIGKILL")
                    try:
                        if process.pid:
                            os.killpg(os.getpgid(process.pid), signal.SIGKILL)
                    except (ProcessLookupError, PermissionError):
                        try:
                            process.send_signal(signal.SIGKILL)
                        except Exception:
                            pass
                    try:
                        await asyncio.wait_for(process.wait(), timeout=2)
                    except Exception as kill_error:
                        task_logger.error(f"Failed to force-kill process group: {kill_error}")
                task_logger.error(f"Task timed out: {e}")
                logs_path = task_logger.save()

                # Structured logging: Timeout (success path logs further below)
                self.structured_logger.log_result(
                    success=False,
                    summary="⏱️ Task timed out",
                    session_id=session_id,
                    task_id=step_id,
                    cli_name=self._strategy.name,
                    model=model,
                    exit_code=-1,
                    error_type="TimeoutError",
                    reason=str(e)[:500],
                )

                return self._attach_worktree_info(
                    NinjaResult(
                        success=False,
                        summary="⏱️ Task timed out",
                        notes=str(e),
                        raw_logs_path=logs_path,
                        exit_code=-1,
                        model_used=model,
                    ),
                    worktree_info,
                )

            task_logger.log_subprocess(cli_result.command, exit_code, stdout, stderr)

            # Parse output using strategy (paths verified against execution_dir,
            # which is the isolation worktree when worktree mode is active)
            parsed = self._strategy.parse_output(stdout, stderr, exit_code, repo_root=execution_dir)

            # Build result from parsed output
            result = self._attach_worktree_info(
                NinjaResult(
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
                ),
                worktree_info,
            )

            task_logger.info(
                f"Task {'succeeded' if result.success else 'failed'}: {result.summary}"
            )

            # Structured logging: Task result
            self.structured_logger.log_result(
                success=result.success,
                summary=result.summary,
                session_id=session_id,
                task_id=step_id,
                cli_name=self._strategy.name,
                model=model,
                touched_paths=result.suspected_touched_paths,
                exit_code=exit_code,
            )

            return result

        except FileNotFoundError:
            task_logger.error(f"Ninja Code CLI not found: {self.config.bin_path}")
            logs_path = task_logger.save()
            # Use locals() to check if model was defined before error
            model_used = locals().get("model", self.config.model)

            # Structured logging: Error
            self.structured_logger.error(
                f"CLI not found: {self.config.bin_path}",
                session_id=session_id,
                task_id=step_id,
                cli_name=self._strategy.name,
                model=model_used,
                bin_path=str(self.config.bin_path),
            )

            return self._attach_worktree_info(
                NinjaResult(
                    success=False,
                    summary="❌ Ninja Code CLI not found",
                    notes=f"Could not find executable: {self.config.bin_path}. "
                    f"Install Ninja Code CLI or set NINJA_CODE_BIN environment variable.",
                    raw_logs_path=logs_path,
                    exit_code=-1,
                    model_used=model_used,
                ),
                worktree_info,
            )
        except Exception as e:
            task_logger.error(f"Unexpected error: {e}")
            logs_path = task_logger.save()
            # Use locals() to check if model was defined before error
            model_used = locals().get("model", self.config.model)

            # Structured logging: Error
            self.structured_logger.error(
                f"Unexpected error: {type(e).__name__}",
                session_id=session_id,
                task_id=step_id,
                cli_name=self._strategy.name,
                model=model_used,
                error_type=type(e).__name__,
                error_message=str(e)[:500],
            )

            return self._attach_worktree_info(
                NinjaResult(
                    success=False,
                    summary="❌ Execution error",
                    notes=str(e)[:200],  # Keep error message concise
                    raw_logs_path=logs_path,
                    exit_code=-1,
                    model_used=model_used,
                ),
                worktree_info,
            )

    async def execute_async_with_opencode_session(
        self,
        repo_root: str,
        step_id: str,
        instruction: dict[str, Any],
        opencode_session_id: str | None = None,
        is_initial: bool = False,
        timeout_sec: int | None = None,
        task_type: str = "quick",
    ) -> NinjaResult:
        """Execute task with OpenCode native session support.

        This method is specifically for OpenCode CLI's --session and --continue flags.
        For Python-based session management, use execute_with_session().

        Legacy path: runs in-place in repo_root with classic safety commits
        (no worktree isolation), because per-call worktrees would break
        session continuity across steps. See NOTE inside the method body.

        Args:
            repo_root: Repository root path.
            step_id: Step identifier.
            instruction: Instruction document.
            opencode_session_id: OpenCode session ID to continue (e.g., "ses_xxxxx").
            is_initial: If True, this is the first step (create new session).
            timeout_sec: Timeout in seconds.
            task_type: Type of task ('quick', 'sequential', 'parallel').

        Returns:
            NinjaResult with session_id field populated if session was created/continued.
        """
        # Check if strategy is OpenCode
        if self._strategy.name != "opencode":
            logger.warning(
                f"execute_async_with_opencode_session() called with {self._strategy.name} strategy. "
                f"Falling back to execute_async() (native sessions only available with OpenCode)"
            )
            return await self.execute_async(
                repo_root=repo_root,
                step_id=step_id,
                instruction=instruction,
                timeout_sec=timeout_sec,
                task_type=task_type,
                session_id=opencode_session_id,
            )

        task_logger = create_task_logger(repo_root, step_id)

        try:
            # NOTE: worktree isolation is intentionally NOT applied here.
            # execute_async_with_opencode_session keeps legacy in-place behavior
            # because OpenCode native sessions (--session/--continue) are stateful:
            # a per-call worktree would give every continuation step a new
            # branch/cwd, breaking session continuity (absolute paths, session
            # storage rooted at repo_root) and orphaning prior steps' branches.
            # To isolate session workflows, use execute_async (single-process
            # plans share one worktree) or set NINJA_WORKTREE_MODE=off to get
            # the legacy auto-commit behavior everywhere. See worktree.py
            # module docstring ("Limitations") and docs/AUTOMATIC_SAFETY.md.
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

            task_logger.info(
                f"Starting OpenCode session task with model: {model} "
                f"(session_id={opencode_session_id}, is_initial={is_initial})"
            )
            task_logger.set_metadata("instruction", instruction)
            task_logger.set_metadata("model", model)
            task_logger.set_metadata("task_type", task_type)
            task_logger.set_metadata("opencode_session_id", opencode_session_id)
            task_logger.set_metadata("is_initial", is_initial)

            # Structured logging: Task start
            self.structured_logger.info(
                f"Starting OpenCode session task: {task_desc[:100]}...",
                session_id=opencode_session_id,
                task_id=step_id,
                cli_name=self._strategy.name,
                model=model,
                task_type=task_type,
                repo_root=repo_root,
                context_file_count=len(context_paths),
                is_initial=is_initial,
            )

            # Build prompt from instruction
            with Path(task_file).open() as f:
                instruction_data = json.load(f)

            prompt = self._build_prompt_text(instruction_data, repo_root)
            file_scope = instruction_data.get("file_scope", {})
            context_paths = file_scope.get("context_paths", [])

            # Build command using strategy with session parameters
            additional_flags = {"use_coding_plan": use_coding_plan} if use_coding_plan else None

            cli_result = self._strategy.build_command(
                prompt=prompt,
                repo_root=repo_root,
                file_paths=context_paths,
                model=model,
                additional_flags=additional_flags,
                session_id=opencode_session_id,
                continue_last=(not is_initial and not opencode_session_id),
            )

            # Log command (redact sensitive data)
            safe_cmd = [
                arg if "api-key" not in prev.lower() else "***REDACTED***"
                for prev, arg in zip(["", *cli_result.command[:-1]], cli_result.command)
            ]
            task_logger.info(f"Running {self._strategy.name}: {' '.join(safe_cmd)}")

            # Structured logging: Command execution
            self.structured_logger.log_command(
                command=cli_result.command,
                session_id=opencode_session_id,
                task_id=step_id,
                cli_name=self._strategy.name,
                model=model,
                working_dir=str(cli_result.working_dir),
            )

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
                limit=SUBPROCESS_STREAM_LIMIT,  # JSON lines can exceed the 64 KiB default
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

            # Parse output using strategy (includes session_id extraction)
            parsed = self._strategy.parse_output(stdout, stderr, exit_code, repo_root=repo_root)

            # Build result from parsed output with session_id
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
                aider_error_detected=parsed.retryable_error,
                session_id=parsed.session_id,  # Include extracted session ID
            )

            # Log session creation/continuation
            if parsed.session_id:
                if is_initial:
                    logger.info(f"✅ Created OpenCode session: {parsed.session_id}")
                    task_logger.info(f"✅ Created OpenCode session: {parsed.session_id}")
                else:
                    logger.info(f"✅ Continued OpenCode session: {parsed.session_id}")
                    task_logger.info(f"✅ Continued OpenCode session: {parsed.session_id}")

            task_logger.info(
                f"Task {'succeeded' if result.success else 'failed'}: {result.summary}"
            )

            # Structured logging: Task result
            self.structured_logger.log_result(
                success=result.success,
                summary=result.summary,
                session_id=parsed.session_id or opencode_session_id,
                task_id=step_id,
                cli_name=self._strategy.name,
                model=model,
                touched_paths=result.suspected_touched_paths,
                exit_code=exit_code,
            )

            return result

        except FileNotFoundError:
            task_logger.error(f"Ninja Code CLI not found: {self.config.bin_path}")
            logs_path = task_logger.save()
            # Use locals() to check if model was defined before error
            model_used = locals().get("model", self.config.model)

            # Structured logging: Error
            self.structured_logger.error(
                f"CLI not found: {self.config.bin_path}",
                session_id=opencode_session_id,
                task_id=step_id,
                cli_name=self._strategy.name,
                model=model_used,
                bin_path=str(self.config.bin_path),
            )

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

            # Structured logging: Error
            self.structured_logger.error(
                f"Unexpected error: {type(e).__name__}",
                session_id=opencode_session_id,
                task_id=step_id,
                cli_name=self._strategy.name,
                model=model_used,
                error_type=type(e).__name__,
                error_message=str(e)[:500],
            )

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
                # Structured logging: Session load failed
                self.structured_logger.error(
                    f"Session not found: {session_id}",
                    session_id=session_id,
                    cli_name=self._strategy.name,
                )

                return NinjaResult(
                    success=False,
                    summary=f"❌ Session {session_id} not found",
                    notes="Session may have been deleted or expired",
                    model_used=self.config.model,
                )

            # Structured logging: Session loaded
            self.structured_logger.log_session(
                action="loaded",
                session_id=session.session_id,
                cli_name=self._strategy.name,
                model=session.model,
                message_count=len(session.messages),
            )
        elif create_session:
            session = self.session_manager.create_session(
                repo_root=repo_root,
                model=self.config.model,
                metadata={"context_paths": context_paths or []},
            )

            # Structured logging: Session created
            self.structured_logger.log_session(
                action="created",
                session_id=session.session_id,
                cli_name=self._strategy.name,
                model=self.config.model,
                repo_root=repo_root,
            )

        # Add user message to session
        if session:
            session.add_message("user", task)
            self.session_manager.save_session(session)
            logger.info(f"📝 Added user message to session {session.session_id}")

            # Structured logging: Session updated
            self.structured_logger.log_session(
                action="updated",
                session_id=session.session_id,
                cli_name=self._strategy.name,
                message_count=len(session.messages),
            )

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
            session_id=session.session_id if session else None,
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

            # Structured logging: Session saved
            self.structured_logger.log_session(
                action="saved",
                session_id=session.session_id,
                cli_name=self._strategy.name,
                model=result.model_used,
                message_count=len(session.messages),
                success=result.success,
            )

        return result


# Backwards compatibility aliases
QwenConfig = NinjaConfig
QwenResult = NinjaResult
QwenDriver = NinjaDriver
