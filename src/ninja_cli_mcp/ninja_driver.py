"""
Ninja Code CLI driver.

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
import shlex
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ninja_cli_mcp.logging_utils import create_task_logger, get_logger
from ninja_cli_mcp.models import ExecutionMode, PlanStep
from ninja_cli_mcp.path_utils import ensure_internal_dirs, safe_join


logger = get_logger(__name__)


# Popular OpenRouter models for code tasks
RECOMMENDED_MODELS = {
    # Claude models
    "anthropic/claude-haiku-4.5-20250929": "Claude Haiku 4.5 - fast and capable",
    "anthropic/claude-sonnet-4": "Claude Sonnet 4 - excellent for complex code",
    "anthropic/claude-3.5-sonnet": "Claude 3.5 Sonnet - previous generation",
    # Qwen models
    "qwen/qwen3-coder": "Qwen3 Coder - optimized for code generation",
    "qwen/qwen-2.5-coder-32b-instruct": "Qwen 2.5 Coder 32B - large coding model",
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

DEFAULT_MODEL = "anthropic/claude-haiku-4.5-20250929"


@dataclass
class NinjaConfig:
    """Configuration for Ninja Code CLI."""

    bin_path: str = "ninja-code"
    openai_base_url: str = "https://openrouter.ai/api/v1"
    openai_api_key: str = ""
    model: str = DEFAULT_MODEL
    timeout_sec: int = 600

    @classmethod
    def from_env(cls) -> NinjaConfig:
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
            "timestamp": datetime.now(UTC).isoformat(),
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

    def _build_command_claude(self, prompt: str, repo_root: str) -> list[str]:  # noqa: ARG002
        """Build command for Claude CLI with secure argument handling."""
        return [
            self.config.bin_path,
            "--print",  # Non-interactive mode
            "--dangerously-skip-permissions",  # Skip permission prompts for automation
            shlex.quote(prompt),  # Properly escape the prompt
        ]

    def _build_command_aider(self, prompt: str, repo_root: str) -> list[str]:  # noqa: ARG002
        """Build command for Aider CLI with secure argument handling."""
        cmd = [
            self.config.bin_path,
            "--yes",  # Auto-accept changes
            "--no-auto-commits",  # Don't auto-commit (let user decide)
            "--model",
            f"openrouter/{self.config.model}",  # OpenRouter model
        ]

        # IMPORTANT: Explicitly pass API key to override aider's cached key
        # Aider caches keys in ~/.aider*/oauth-keys.env and might use that instead
        if self.config.openai_api_key:
            cmd.extend(
                [
                    "--openai-api-key",
                    self.config.openai_api_key,  # Force our key
                    "--openai-api-base",
                    self.config.openai_base_url,  # Force OpenRouter
                ]
            )

        # Add conservative limits to avoid incomplete responses
        cmd.extend(
            [
                "--max-chat-history-tokens",
                "8000",  # Limit context to avoid token limits
                "--timeout",
                "120",  # 2 minute timeout for API calls
            ]
        )

        cmd.extend(["--message", shlex.quote(prompt)])  # Properly escape the prompt

        return cmd

    def _build_command_qwen(self, prompt: str, repo_root: str) -> list[str]:  # noqa: ARG002
        """Build command for Qwen Code CLI with secure argument handling."""
        return [
            self.config.bin_path,
            "--non-interactive",
            "--message",
            shlex.quote(prompt),  # Properly escape the prompt
        ]

    def _build_command_generic(self, prompt: str, repo_root: str) -> list[str]:  # noqa: ARG002
        """Build command for generic/unknown CLI with secure argument handling."""
        # Try a common pattern with proper escaping
        return [
            self.config.bin_path,
            shlex.quote(prompt),  # Properly escape the prompt
        ]

    def _build_command(self, task_file: Path, repo_root: str) -> list[str]:
        """
        Build the command to run AI Code CLI.

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

        # Detect CLI type and build appropriate command
        cli_type = self._detect_cli_type()
        logger.debug(f"Detected CLI type: {cli_type}")

        if cli_type == "aider":
            return self._build_command_aider(prompt, repo_root)
        elif cli_type == "qwen":
            return self._build_command_qwen(prompt, repo_root)
        elif cli_type == "claude":
            return self._build_command_claude(prompt, repo_root)
        elif cli_type == "gemini":
            return self._build_command_qwen(prompt, repo_root)  # Similar to Qwen
        else:
            return self._build_command_generic(prompt, repo_root)

    def _parse_output(self, stdout: str, stderr: str, exit_code: int) -> NinjaResult:
        """
        Parse Ninja Code CLI output to extract CONCISE results.

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

        # Extract file changes (what was modified)
        suspected_paths: list[str] = []
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
        if not success and stderr:
            # Extract just the error message, not full stack traces
            error_lines = [line.strip() for line in stderr.split("\n") if line.strip()]
            # Look for common error indicators
            for line in error_lines[-10:]:  # Last 10 lines only
                lower = line.lower()
                if any(indicator in lower for indicator in ["error:", "failed:", "exception:", "traceback"]):
                    notes = line[:200]  # Max 200 chars
                    break
            
            if not notes and error_lines:
                notes = error_lines[-1][:200]  # Last line, max 200 chars

            # Detect specific OpenRouter/API errors
            if "finish_reason" in stderr.lower():
                notes = "⚠️ Incomplete API response (token limit or timeout). Try smaller context or different model."

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
        )

    def _create_isolated_workdir(self, repo_root: str, step_id: str) -> Path:
        """
        Create an isolated working directory for the task.

        Args:
            repo_root: Repository root path.
            step_id: Step identifier.

        Returns:
            Path to the isolated working directory.
        """
        dirs = ensure_internal_dirs(repo_root)
        workdir_path = safe_join(dirs["work"], f"task_{step_id}")

        # Create the isolated work directory
        workdir_path.mkdir(parents=True, exist_ok=True)

        logger.debug(f"Created isolated work directory: {workdir_path}")
        return workdir_path

    def _sync_workdir_to_repo(self, workdir_path: Path, repo_root: Path, task_logger) -> None:
        """
        Sync modified files from isolated work directory back to target repo.

        Args:
            workdir_path: Path to isolated work directory
            repo_root: Path to target repository
            task_logger: Logger instance
        """

        if not workdir_path.exists():
            return

        try:
            # Copy all files from work dir to repo (excluding .git, .ninja-cli-mcp, etc)
            for item in workdir_path.rglob("*"):
                if item.is_file():
                    # Skip hidden dirs and internal files
                    relative_parts = item.relative_to(workdir_path).parts
                    if any(part.startswith(".") for part in relative_parts):
                        continue

                    target_path = repo_root / item.relative_to(workdir_path)
                    target_path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(item, target_path)
                    task_logger.debug(f"Synced: {item.relative_to(workdir_path)} -> {target_path}")

        except Exception as e:
            task_logger.warning(f"Failed to sync work directory to repo: {e}")

    def _cleanup_isolated_workdir(self, workdir_path: Path) -> None:
        """
        Clean up the isolated working directory after execution.

        Args:
            workdir_path: Path to the isolated working directory.
        """
        try:
            if workdir_path.exists():
                shutil.rmtree(workdir_path)
                logger.debug(f"Cleaned up isolated work directory: {workdir_path}")
        except Exception as e:
            logger.warning(f"Failed to clean up isolated work directory {workdir_path}: {e}")

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

        # Create isolated working directory
        workdir_path = self._create_isolated_workdir(repo_root, step_id)
        task_logger.info(f"Using isolated work directory: {workdir_path}")

        try:
            # Write task file
            task_file = self._write_task_file(repo_root, step_id, instruction)
            task_logger.info(f"Wrote task file: {task_file}")

            # Build command
            cmd = self._build_command(task_file, str(workdir_path))
            task_logger.info(f"Running command: {' '.join(cmd)}")

            # Get environment
            env = self._get_env()

            # Execute
            timeout = timeout_sec or self.config.timeout_sec
            process = subprocess.run(
                cmd,
                check=False, cwd=str(workdir_path),  # Execute in isolated work directory
                env=env,
                capture_output=True,
                text=True,
                timeout=timeout,
            )

            task_logger.log_subprocess(cmd, process.returncode, process.stdout, process.stderr)

            # Parse result (extracts CONCISE summary only)
            result = self._parse_output(process.stdout, process.stderr, process.returncode)
            result.raw_logs_path = task_logger.save()

            task_logger.info(
                f"Task {'succeeded' if result.success else 'failed'}: {result.summary}"
            )

            # Copy modified files back to target repo before cleanup
            if result.success:
                self._sync_workdir_to_repo(workdir_path, Path(repo_root), task_logger)

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
        finally:
            # Clean up isolated work directory
            self._cleanup_isolated_workdir(workdir_path)

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

        # Create isolated working directory
        workdir_path = self._create_isolated_workdir(repo_root, step_id)
        task_logger.info(f"Using isolated work directory: {workdir_path}")

        try:
            # Write task file
            task_file = self._write_task_file(repo_root, step_id, instruction)
            task_logger.info(f"Wrote task file: {task_file}")

            # Build command
            cmd = self._build_command(task_file, str(workdir_path))
            task_logger.info(f"Running command: {' '.join(cmd)}")

            # Get environment
            env = self._get_env()

            # Execute asynchronously
            timeout = timeout_sec or self.config.timeout_sec

            process = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=str(workdir_path),  # Execute in isolated work directory
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
                    model_used=self.config.model,
                )

            task_logger.log_subprocess(cmd, exit_code, stdout, stderr)

            # Parse result (extracts CONCISE summary only)
            result = self._parse_output(stdout, stderr, exit_code)
            result.raw_logs_path = task_logger.save()

            task_logger.info(
                f"Task {'succeeded' if result.success else 'failed'}: {result.summary}"
            )

            # Copy modified files back to target repo before cleanup
            if result.success:
                self._sync_workdir_to_repo(workdir_path, Path(repo_root), task_logger)

            return result

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
        finally:
            # Clean up isolated work directory
            self._cleanup_isolated_workdir(workdir_path)


# Backwards compatibility aliases
QwenConfig = NinjaConfig
QwenResult = NinjaResult
QwenDriver = NinjaDriver
