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

# Daemon removed - using simple subprocess mode for reliability
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

    Execution Mode:
        Uses simple subprocess mode - spawns opencode run for each task.
        No daemon, no server management, no session complexity.
        Clean and reliable execution.
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

        # Check if OpenCode server is enabled via environment
        # Server mode removed - using simple subprocess execution

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
        session_id: str | None = None,
        continue_last: bool = False,
    ) -> CLICommandResult:
        """Build OpenCode command with z.ai endpoint support.

        Args:
            prompt: The instruction prompt.
            repo_root: Repository root path.
            file_paths: List of files to include in context.
            model: Model to use (if None, use configured default).
            additional_flags: Additional flags including:
                - use_coding_plan: Whether to use Coding Plan API (bool)
                - enable_multi_agent: Whether to add ultrawork keyword (bool)
            session_id: OpenCode session ID to continue (optional).
            continue_last: Continue last session (optional).

        Returns:
            CLICommandResult with command, env, and metadata.
        """
        model_name = model or self.config.model
        use_coding_plan = (
            additional_flags.get("use_coding_plan", False) if additional_flags else False
        )
        enable_multi_agent = (
            additional_flags.get("enable_multi_agent", False) if additional_flags else False
        )

        # OpenCode supports direct provider access (anthropic/, openai/, google/)
        # and also supports openrouter/ prefix for OpenRouter models
        # Do NOT add openrouter/ prefix if model already has a provider prefix
        # Model format: provider/model (e.g., anthropic/claude-sonnet-4-5)
        # OpenCode will use native API if available, fallback to OpenRouter if not

        # Simple command - no daemon, no session management, no broken --attach
        # Just run opencode directly and let it handle everything
        cmd = [
            self.bin_path,
            "run",
            "--model",
            model_name,
        ]

        # Session support (if explicitly requested)
        if session_id:
            cmd.extend(["--session", session_id])
        elif continue_last:
            cmd.append("--continue")

        # Build enhanced prompt with file context
        # NOTE: We don't use --file flag because it causes OpenCode to interpret
        # the message differently. Instead, we mention files in the prompt and
        # let OpenCode discover them automatically.
        final_prompt = prompt
        if file_paths:
            files_text = ", ".join(file_paths)
            final_prompt = f"{prompt}\n\nFocus on these files: {files_text}"

        # Multi-agent activation (add ultrawork to prompt)
        if enable_multi_agent and "ultrawork" not in final_prompt.lower():
            final_prompt = f"{final_prompt}\n\nultrawork"
            logger.info("🤖 Multi-agent mode activated (ultrawork)")

        # Prompt as positional argument
        cmd.append(final_prompt)

        # Build environment (inherit current environment)
        env = os.environ.copy()

        # Determine timeout based on task type
        # Multi-agent tasks may need more time
        base_timeout = int(os.environ.get("NINJA_OPENCODE_TIMEOUT", "600"))
        timeout = base_timeout * 2 if enable_multi_agent else base_timeout

        return CLICommandResult(
            command=cmd,
            env=env,
            working_dir=Path(repo_root),
            metadata={
                "provider": "z.ai" if self._is_zai_model(model_name) else "generic",
                "coding_plan_api": use_coding_plan,
                "multi_agent": enable_multi_agent,
                "model": model_name,
                "timeout": timeout,
                "session_id": session_id,
                "continue_last": continue_last,
            },
        )

    def build_command_with_multi_agent(
        self,
        prompt: str,
        repo_root: str,
        agents: list[str],
        context: dict[str, Any] | None = None,
        file_paths: list[str] | None = None,
        model: str | None = None,
    ) -> CLICommandResult:
        """Build OpenCode command with multi-agent orchestration.

        Args:
            prompt: The original task description.
            repo_root: Repository root path.
            agents: List of agent names to activate.
            context: Additional context for agents.
            file_paths: List of files to include in context.
            model: Model to use (if None, use configured default).

        Returns:
            CLICommandResult with enhanced multi-agent prompt.
        """
        # Import here to avoid circular dependency
        from ninja_coder.multi_agent import MultiAgentOrchestrator

        orchestrator = MultiAgentOrchestrator(self)
        enhanced_prompt = orchestrator.build_ultrawork_prompt(prompt, agents, context)

        return self.build_command(
            prompt=enhanced_prompt,
            repo_root=repo_root,
            file_paths=file_paths,
            model=model,
            additional_flags={"enable_multi_agent": True},
        )

    def parse_output(
        self,
        stdout: str,
        stderr: str,
        exit_code: int,
        repo_root: str | None = None,
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

        # OpenCode-specific error patterns (comprehensive)
        error_patterns = [
            # Authentication and authorization errors (HIGH PRIORITY)
            r"AuthenticationError",
            r"authentication\s+failed",
            r"User\s+not\s+found",
            r"Unauthorized",
            r"401",
            r"403\s+Forbidden",
            r"invalid\s+api\s+key",
            r"api\s+key.*?(not\s+found|invalid|missing)",
            # Credit and billing errors (HIGH PRIORITY)
            r"insufficient\s+credits",
            r"requires\s+more\s+credits",
            r"can\s+only\s+afford",
            r"credit\s+limit",
            r"billing\s+error",
            r"payment\s+required",
            # General API errors (HIGH PRIORITY)
            r"APIError",
            r"OpenrouterException",
            r"litellm\..*?Error",
            r"API\s+request\s+failed",
            r"api\s+error",
            # Rate limiting and timeouts
            r"rate\s+limit",
            r"timeout",
            r"connection\s+refused",
            # Model errors
            r"model\s+not\s+found",
            r"invalid\s+model",
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
        # First, strip ANSI color codes for easier pattern matching
        ansi_escape = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
        clean_output = ansi_escape.sub("", combined_output)

        suspected_paths: list[str] = []
        file_patterns = [
            r"(?:wrote|created|modified|updated|edited)\s+['\"]?([^\s'\"]+)['\"]?",
            r"(?:writing|creating|modifying|updating|editing)\s+['\"]?([^\s'\"]+)['\"]?",
            r"file:\s*['\"]?([^\s'\"]+)['\"]?",
            # OpenCode-specific tool call format: "← Write filename.py" or "| Edit filename.py"
            r"[←\|]\s+(?:Edit|Write|NotebookEdit)\s+([^\s]+)",
        ]
        for pattern in file_patterns:
            matches = re.findall(pattern, clean_output, re.IGNORECASE)
            for match in matches:
                if match and ("/" in match or "." in match):
                    suspected_paths.append(match)

        # Deduplicate paths
        suspected_paths = list(set(suspected_paths))

        # Extract session ID from output
        session_id = None
        session_patterns = [
            r"Session:\s+(\S+)",
            r"session.*?:\s*(\S+)",
            r"session[_-]id[:\s]+(\S+)",
        ]
        for pattern in session_patterns:
            match = re.search(pattern, clean_output, re.IGNORECASE)
            if match:
                session_id = match.group(1)
                logger.debug(f"Extracted session ID: {session_id}")
                break

        # Git-based file change detection (more reliable than output parsing)
        # This runs after regex-based detection to catch files that weren't mentioned in output
        if success and repo_root:
            try:
                import subprocess
                git_files = []

                logger.debug(f"Running git-based file detection in {repo_root}")

                # Check for modified tracked files
                result = subprocess.run(
                    ["git", "diff", "--name-only", "HEAD"],
                    cwd=repo_root,
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                logger.debug(f"git diff returncode={result.returncode}, stdout_len={len(result.stdout)}")
                if result.returncode == 0 and result.stdout.strip():
                    modified_files = [f.strip() for f in result.stdout.split('\n') if f.strip()]
                    git_files.extend(modified_files)
                    logger.debug(f"Found {len(modified_files)} modified files: {modified_files}")

                # Check for new untracked files (this is what was missing!)
                result = subprocess.run(
                    ["git", "ls-files", "--others", "--exclude-standard"],
                    cwd=repo_root,
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                logger.debug(f"git ls-files returncode={result.returncode}, stdout_len={len(result.stdout)}")
                if result.returncode == 0 and result.stdout.strip():
                    untracked_files = [f.strip() for f in result.stdout.split('\n') if f.strip()]
                    git_files.extend(untracked_files)
                    logger.debug(f"Found {len(untracked_files)} untracked files: {untracked_files}")

                # Add git-detected files that weren't already found by regex
                for git_file in git_files:
                    if git_file not in suspected_paths:
                        suspected_paths.append(git_file)
                        logger.debug(f"Added git-detected file: {git_file}")

                if git_files:
                    logger.info(f"✓ Git detected {len(git_files)} modified/new files: {git_files}")
                else:
                    logger.warning(f"⚠️ Git detection found no files (repo_root={repo_root})")
            except Exception as e:
                # Git detection failure is non-critical, just log it
                logger.warning(f"Git-based file detection failed (non-critical): {e}")

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
            # Priority 0: Authentication and credit errors (most critical)
            if any(
                pattern in combined_output
                for pattern in [
                    "AuthenticationError",
                    "User not found",
                    "Unauthorized",
                    "401",
                ]
            ):
                notes = "❌ Authentication failed. Check OPENROUTER_API_KEY in ~/.ninja-mcp.env or verify account status."
                summary = "❌ Authentication error"
            elif any(
                pattern in combined_output
                for pattern in ["insufficient credits", "requires more credits", "can only afford"]
            ):
                notes = "💰 Insufficient credits. Add credits at https://openrouter.ai/settings/keys or reduce max_tokens."
                summary = "❌ Insufficient credits"
            # Priority 1: Error message from pattern matching
            elif error_msg:
                notes = error_msg[:200]
            # Priority 2: Last line from stderr
            elif stderr:
                error_lines = [line.strip() for line in stderr.split("\n") if line.strip()]
                if error_lines:
                    notes = error_lines[-1][:200]

        # Final validation: If we claim success but no files were touched, it's suspicious
        # NOTE: Git-based detection above should catch most cases, so this is a backup check
        if success and not suspected_paths and len(combined_output) > 100:
            # Only check STDOUT (actual output), not combined_output which includes the prompt
            # The prompt always contains action keywords, causing false positives
            action_keywords = ["wrote", "created", "modified", "updated", "edited"]
            has_action_in_output = any(
                keyword in stdout.lower() for keyword in action_keywords
            )

            # If output explicitly mentions file operations but git found nothing, warn
            if has_action_in_output:
                success = False
                summary = "⚠️ Task completed but no files were modified"
                notes = (
                    "CLI exited successfully but no file changes detected. Check logs for details."
                )
                logger.warning("Suspicious success: exit_code=0 but no files touched")

        # CRITICAL BUG DETECTION: Check for corrupted file content (Python list literals)
        # OpenCode has a known bug where it sometimes writes list representations instead of actual content
        # This happens during sequential/parallel execution when file content gets split into a list
        # and that list representation is written to the file instead of joining the strings.
        if success and suspected_paths:
            import os
            from pathlib import Path

            corrupted_files = []
            for file_path in suspected_paths:
                try:
                    # Convert to absolute path if relative
                    if not os.path.isabs(file_path):
                        # Try with repo_root
                        if repo_root:
                            path_obj = Path(repo_root) / file_path
                        else:
                            continue
                    else:
                        path_obj = Path(file_path)
                    if not path_obj.exists() or not path_obj.is_file():
                        continue

                    # Read first few characters to detect corruption pattern
                    with open(path_obj, 'r') as f:
                        first_chars = f.read(100).strip()

                    # Check for Python list literal at start of file (corruption pattern)
                    # Pattern: starts with [ (could be on its own line)
                    if first_chars.startswith('['):
                        # Read full content to verify it's a list literal
                        with open(path_obj, 'r') as f:
                            content = f.read().strip()

                        # Try to parse as Python literal
                        try:
                            import ast
                            parsed = ast.literal_eval(content)

                            # If it's a list of strings, it's corrupted
                            if isinstance(parsed, list) and len(parsed) > 0:
                                if all(isinstance(item, str) for item in parsed):
                                    logger.error(
                                        f"🐛 CORRUPTION DETECTED: {file_path} contains list literal instead of code"
                                    )
                                    corrupted_files.append(str(file_path))

                                    # AUTO-FIX: Join the strings and rewrite the file
                                    fixed_content = "".join(parsed)
                                    with open(path_obj, 'w') as f:
                                        f.write(fixed_content)
                                    logger.info(f"✅ AUTO-FIXED: Joined {len(parsed)} strings and rewrote {file_path}")
                        except (ValueError, SyntaxError):
                            # Not a valid Python literal, probably fine
                            pass
                except Exception as e:
                    # Don't fail the whole task due to corruption detection issues
                    logger.warning(f"Failed to check {file_path} for corruption: {e}")

            # If corruption was detected and fixed, update the notes
            if corrupted_files:
                corruption_note = (
                    f"⚠️ CORRUPTION DETECTED & AUTO-FIXED: {len(corrupted_files)} file(s) contained "
                    f"Python list literals instead of actual code. This is a known OpenCode bug. "
                    f"Files have been automatically repaired by joining the string fragments."
                )
                notes = f"{notes}\n{corruption_note}" if notes else corruption_note
                logger.warning(corruption_note)

        return ParsedResult(
            success=success,
            summary=summary,
            notes=notes,
            touched_paths=suspected_paths,
            retryable_error=retryable_error,
            session_id=session_id,
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
        """Get recommended timeout for task type.

        With daemon mode, use activity-based timeout (see driver.py).
        These are maximum timeouts - actual timeout is based on output activity.

        Args:
            task_type: Type of task ('quick', 'sequential', 'parallel').

        Returns:
            Timeout in seconds.
        """
        # Daemon mode is much faster but still needs generous timeouts for complex tasks
        return {
            "quick": 300,  # 5 minutes (was 180s)
            "sequential": 900,  # 15 minutes (was 600s)
            "parallel": 1200,  # 20 minutes (was 900s)
        }.get(task_type, 600)

    def _is_zai_model(self, model_name: str) -> bool:
        """Check if model is a z.ai model.

        Args:
            model_name: Model name to check.

        Returns:
            True if model is from z.ai (Zhipu AI / GLM models).
        """
        model_lower = model_name.lower()
        return "zhipu" in model_lower or "glm" in model_lower
