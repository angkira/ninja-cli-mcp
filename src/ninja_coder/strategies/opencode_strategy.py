"""
OpenCode CLI strategy implementation with native z.ai support.

This module implements the CLI strategy for OpenCode, providing native
support for z.ai API endpoints including the Coding Plan API.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ninja_coder.strategies.base import (
    CLICapabilities,
    CLICommandResult,
    ParsedResult,
)
from ninja_common.logging_utils import get_logger


if TYPE_CHECKING:
    from ninja_coder.driver import NinjaConfig

logger = get_logger(__name__)


class DialogueSession:
    """Manages a persistent dialogue session for multi-turn conversations."""

    def __init__(self, initial_system_prompt: str = ""):
        """Initialize dialogue session.

        Args:
            initial_system_prompt: System prompt to start conversation with.
        """
        self.messages: list[dict[str, str]] = []
        if initial_system_prompt:
            self.messages.append({"role": "system", "content": initial_system_prompt})

    def add_user_message(self, content: str) -> None:
        """Add a user message to the conversation.

        Args:
            content: User message content.
        """
        self.messages.append({"role": "user", "content": content})

    def add_assistant_message(self, content: str) -> None:
        """Add an assistant message to the conversation.

        Args:
            content: Assistant message content.
        """
        self.messages.append({"role": "assistant", "content": content})

    def get_conversation_history(self) -> list[dict[str, str]]:
        """Get full conversation history for API request.

        Returns:
            List of message dicts with 'role' and 'content' keys.
        """
        return self.messages

    def get_last_response(self) -> str | None:
        """Get the last assistant response.

        Returns:
            Last assistant message content or None if no assistant messages.
        """
        for msg in reversed(self.messages):
            if msg.get("role") == "assistant":
                return msg.get("content", "")
        return None


class OpenCodeStrategy:
    """Strategy for OpenCode CLI tool with native z.ai support.

    OpenCode is optimized for parallel tasks and supports 75+ providers
    including native z.ai integration with Coding Plan API.

    Dialogue mode allows persistent conversation across multiple sequential steps.
    """

    def __init__(self, bin_path: str, config: NinjaConfig):
        """Initialize OpenCode strategy.

        Args:
            bin_path: Path to the OpenCode binary.
            config: Ninja configuration object.
        """
        self.bin_path = bin_path
        self.config = config
        self._session: DialogueSession | None = None
        self._capabilities = CLICapabilities(
            supports_streaming=True,
            supports_file_context=True,
            supports_model_routing=True,  # 75+ providers
            supports_native_zai=True,  # Native z.ai endpoint support
            supports_dialogue_mode=True,  # Supports persistent dialogue sessions
            max_context_files=100,
            preferred_task_types=["parallel", "sequential"],  # Also supports sequential
        )

    @property
    def name(self) -> str:
        """CLI tool name."""
        return "opencode"

    @property
    def capabilities(self) -> CLICapabilities:
        """Return capabilities of OpenCode CLI."""
        return self._capabilities

    def build_command(
        self,
        prompt: str,
        repo_root: str,
        file_paths: list[str] | None = None,
        model: str | None = None,
        additional_flags: dict[str, Any] | None = None,
    ) -> CLICommandResult:
        """Build OpenCode command with z.ai endpoint support.

        Args:
            prompt: The instruction prompt.
            repo_root: Repository root path.
            file_paths: List of files to include in context.
            model: Model to use (if None, use configured default).
            additional_flags: Additional flags including:
                - use_coding_plan: Whether to use Coding Plan API (bool)

        Returns:
            CLICommandResult with command, env, and metadata.
        """
        model_name = model or self.config.model
        use_coding_plan = (
            additional_flags.get("use_coding_plan", False) if additional_flags else False
        )

        cmd = [
            self.bin_path,
            "--non-interactive",
            "--model",
            model_name,
        ]

        # Z.ai endpoint selection
        # Note: OpenCode may have different CLI arguments - this is a reference implementation
        # Adjust based on actual OpenCode CLI interface
        if self._is_zai_model(model_name):
            if use_coding_plan:
                # Coding Plan API endpoint for advanced coding tasks
                base_url = "https://open.bigmodel.cn/api/coding/paas/v4"
                logger.info(f"Using z.ai Coding Plan API for model {model_name}")
            else:
                # Standard API endpoint
                base_url = "https://open.bigmodel.cn/api/paas/v4"
                logger.info(f"Using z.ai standard API for model {model_name}")

            cmd.extend(["--base-url", base_url])
        elif self.config.openai_base_url:
            # Other providers via OpenCode's native routing
            cmd.extend(["--base-url", self.config.openai_base_url])

        # API key
        if self.config.openai_api_key:
            cmd.extend(["--api-key", self.config.openai_api_key])

        # File context
        if file_paths:
            for file_path in file_paths:
                cmd.extend(["--file", file_path])

        # Prompt
        cmd.extend(["--message", prompt])

        # Build environment (inherit current environment)
        env = os.environ.copy()

        # Determine timeout based on task type
        # OpenCode typically has different timeout needs than Aider
        timeout = int(os.environ.get("NINJA_OPENCODE_TIMEOUT", "600"))

        return CLICommandResult(
            command=cmd,
            env=env,
            working_dir=Path(repo_root),
            metadata={
                "provider": "z.ai" if self._is_zai_model(model_name) else "generic",
                "coding_plan_api": use_coding_plan,
                "model": model_name,
                "timeout": timeout,
            },
        )

    def parse_output(
        self,
        stdout: str,
        stderr: str,
        exit_code: int,
    ) -> ParsedResult:
        """Parse OpenCode output.

        OpenCode has simpler error patterns than Aider and more reliable
        exit codes.

        Args:
            stdout: Standard output from OpenCode execution.
            stderr: Standard error from OpenCode execution.
            exit_code: Exit code from OpenCode execution.

        Returns:
            ParsedResult with success status, summary, and file changes.
        """
        success = exit_code == 0
        combined_output = stdout + "\n" + stderr

        # OpenCode-specific error patterns (simpler than Aider)
        error_patterns = [
            r"api\s+error",
            r"rate\s+limit",
            r"timeout",
            r"connection\s+refused",
            r"authentication\s+failed",
            r"model\s+not\s+found",
            r"invalid\s+api\s+key",
        ]

        retryable_error = False
        error_msg = ""

        for pattern in error_patterns:
            match = re.search(pattern, combined_output, re.IGNORECASE)
            if match:
                # Rate limits and timeouts are retryable
                if any(
                    retry_pattern in pattern
                    for retry_pattern in [r"rate\s+limit", "timeout", r"connection\s+refused"]
                ):
                    retryable_error = True

                # Extract context around the error
                start = max(0, match.start() - 60)
                end = min(len(combined_output), match.end() + 60)
                error_msg = combined_output[start:end].strip()
                error_msg = " ".join(error_msg.split())
                break

        # Extract file changes (similar pattern to Aider)
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

        # Build summary
        if success:
            if suspected_paths:
                file_count = len(suspected_paths)
                file_list = ", ".join(suspected_paths[:5])
                if file_count > 5:
                    file_list += f" and {file_count - 5} more"
                summary = f"✅ Modified {file_count} file(s): {file_list}"
            else:
                summary = "✅ Task completed successfully"
        elif error_msg:
            summary = f"❌ OpenCode failed: {error_msg[:100]}"
        else:
            summary = "❌ Task failed"

        # Build notes from error messages
        notes = ""
        if not success:
            if error_msg:
                notes = error_msg[:200]
            elif stderr:
                error_lines = [line.strip() for line in stderr.split("\n") if line.strip()]
                if error_lines:
                    notes = error_lines[-1][:200]

        return ParsedResult(
            success=success,
            summary=summary,
            notes=notes,
            touched_paths=suspected_paths,
            retryable_error=retryable_error,
        )

    def should_retry(
        self,
        stdout: str,
        stderr: str,
        exit_code: int,
    ) -> bool:
        """Determine if OpenCode execution should be retried.

        Args:
            stdout: Standard output from execution.
            stderr: Standard error from execution.
            exit_code: Exit code from execution.

        Returns:
            True if the error is retryable, False otherwise.
        """
        result = self.parse_output(stdout, stderr, exit_code)
        return result.retryable_error

    def start_dialogue_session(self, system_prompt: str = "") -> DialogueSession:
        """Start a new dialogue session for multi-turn conversation.

        This creates a new session that maintains conversation history
        across multiple sequential steps, preserving context and improving quality.

        Args:
            system_prompt: Optional system prompt for the conversation.

        Returns:
            New DialogueSession instance.
        """
        self._session = DialogueSession(system_prompt)
        return self._session

    def end_dialogue_session(self) -> None:
        """End the current dialogue session.

        Clears the active session, releasing conversation memory.
        """
        self._session = None

    def send_in_dialogue(
        self, prompt: str, model: str | None = None
    ) -> tuple[str, list[dict[str, str]]]:
        """Send a message within the active dialogue session.

        Maintains conversation history by appending user message and
        preparing message list for API request including all prior context.

        Args:
            prompt: The prompt/message to send.
            model: Optional model override (uses configured model if None).

        Returns:
            Tuple of (formatted_prompt, full_message_history).
        """
        if self._session is None:
            raise RuntimeError("No active dialogue session. Call start_dialogue_session() first.")

        self._session.add_user_message(prompt)
        message_history = self._session.get_conversation_history()

        # Format as multiline message for API
        formatted_prompt = self._format_conversation_as_prompt(message_history)

        return formatted_prompt, message_history

    def _format_conversation_as_prompt(self, messages: list[dict[str, str]]) -> str:
        """Format conversation history as a multi-line prompt.

        This is used when the CLI doesn't support direct message array.

        Args:
            messages: List of message dicts with 'role' and 'content' keys.

        Returns:
            Formatted prompt string with conversation history.
        """
        prompt_lines = []
        for msg in messages:
            role = msg.get("role", "").upper()
            content = msg.get("content", "")
            if role == "SYSTEM":
                prompt_lines.append(f"[SYSTEM]\n{content}")
            elif role == "USER":
                prompt_lines.append(f"[USER]\n{content}")
            elif role == "ASSISTANT":
                prompt_lines.append(f"[ASSISTANT]\n{content}")
        return "\n\n".join(prompt_lines)

    def get_timeout(self, task_type: str) -> int:
        """Get timeout for OpenCode based on task type.

        OpenCode is optimized for parallel tasks and can handle them efficiently.

        Args:
            task_type: Type of task ('quick', 'sequential', 'parallel').

        Returns:
            Timeout in seconds.
        """
        base_timeout = int(os.environ.get("NINJA_OPENCODE_TIMEOUT", "600"))

        if task_type == "parallel":
            # OpenCode excels at parallel, use full timeout
            return base_timeout
        elif task_type == "quick":
            # Quick tasks can be faster
            return base_timeout // 2

        return base_timeout

    def _is_zai_model(self, model_name: str) -> bool:
        """Check if model is a z.ai model.

        Args:
            model_name: Model name to check.

        Returns:
            True if model is from z.ai (Zhipu AI / GLM models).
        """
        model_lower = model_name.lower()
        return "zhipu" in model_lower or "glm" in model_lower

    def start_dialogue_session(self, system_prompt: str = "") -> DialogueSession:
        """Start a new dialogue session for multi-turn conversation.

        Args:
            system_prompt: Optional system prompt for the conversation.

        Returns:
            New DialogueSession instance.
        """
        self._session = DialogueSession(system_prompt)
        return self._session

    def end_dialogue_session(self) -> None:
        """End current dialogue session.

        Clears any active session state.
        """
        self._session = None

    def send_in_dialogue(
        self, prompt: str, model: str | None = None
    ) -> tuple[str, list[dict[str, str]]]:
        """Send a message within an active dialogue session.

        Maintains conversation history by appending user message and
        preparing message list for API request including all prior context.

        Args:
            prompt: The message to send.
            model: Optional model override (uses configured model if None).

        Returns:
            Tuple of (formatted_prompt, full_message_history).

        Raises:
            RuntimeError: If no active dialogue session exists.
        """
        if self._session is None:
            raise RuntimeError("No active dialogue session. Call start_dialogue_session() first.")

        self._session.add_user_message(prompt)
        message_history = self._session.get_conversation_history()

        # Format as multiline message for API
        formatted_prompt = self._format_conversation_as_prompt(message_history)

        return formatted_prompt, message_history
