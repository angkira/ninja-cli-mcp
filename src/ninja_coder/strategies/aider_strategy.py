"""
Aider CLI strategy implementation.

This module implements the CLI strategy for Aider, migrating all Aider-specific
logic from the original NinjaDriver implementation.
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
from ninja_common.defaults import FALLBACK_CODER_MODELS
from ninja_common.logging_utils import get_logger
from ninja_common.path_utils import ensure_internal_dirs, safe_join


if TYPE_CHECKING:
    from ninja_coder.driver import NinjaConfig

logger = get_logger(__name__)


class AiderStrategy:
    """Strategy for Aider CLI tool.

    This strategy encapsulates all Aider-specific logic including:
    - Command building with OpenRouter integration
    - Provider preference via YAML settings
    - Comprehensive error detection (13 patterns)
    - Timeout configuration
    """

    def __init__(self, bin_path: str, config: NinjaConfig):
        """Initialize Aider strategy.

        Args:
            bin_path: Path to the Aider binary.
            config: Ninja configuration object.
        """
        self.bin_path = bin_path
        self.config = config
        self._capabilities = CLICapabilities(
            supports_streaming=True,
            supports_file_context=True,
            supports_model_routing=True,  # via OpenRouter
            supports_native_zai=False,
            max_context_files=50,
            preferred_task_types=["sequential", "quick"],
        )

    @property
    def name(self) -> str:
        """CLI tool name."""
        return "aider"

    @property
    def capabilities(self) -> CLICapabilities:
        """Return capabilities of Aider CLI."""
        return self._capabilities

    def build_command(
        self,
        prompt: str,
        repo_root: str,
        file_paths: list[str] | None = None,
        model: str | None = None,
        additional_flags: dict[str, Any] | None = None,
    ) -> CLICommandResult:
        """Build Aider command with OpenRouter integration.

        Args:
            prompt: The instruction prompt.
            repo_root: Repository root path.
            file_paths: List of files to include in context.
            model: Model to use (if None, use configured default).
            additional_flags: Additional CLI-specific flags (unused for Aider).

        Returns:
            CLICommandResult with command, env, and metadata.

        Raises:
            ValueError: If no API key is configured.
        """
        model_name = model or self.config.model

        cmd = [
            self.bin_path,
            "--yes",  # Auto-accept changes
            "--no-auto-commits",  # Don't auto-commit (let user decide)
            "--no-git",  # Disable git operations (prevents hangs)
            "--no-pretty",  # Disable pretty output (prevents buffering issues)
            "--no-stream",  # Disable streaming (cleaner output)
            "--no-suggest-shell-commands",  # Don't suggest shell commands
            "--no-check-update",  # Don't check for updates
            "--model",
            f"openrouter/{model_name}",  # OpenRouter model
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
                        "name": f"openrouter/{model_name}",
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
                # Use --file to add files to aider's context
                cmd.extend(["--file", file_path])

        # Note: No shlex.quote needed - subprocess with list args doesn't use shell
        cmd.extend(["--message", prompt])

        # Build environment (inherit current environment)
        env = os.environ.copy()

        return CLICommandResult(
            command=cmd,
            env=env,
            working_dir=Path(repo_root),
            metadata={
                "timeout": int(aider_timeout),
                "max_context_tokens": 8000,
                "model": model_name,
            },
        )

    def parse_output(
        self,
        stdout: str,
        stderr: str,
        exit_code: int,
    ) -> ParsedResult:
        """Parse Aider output with comprehensive error detection.

        Args:
            stdout: Standard output from Aider execution.
            stderr: Standard error from Aider execution.
            exit_code: Exit code from Aider execution.

        Returns:
            ParsedResult with success status, summary, and file changes.
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

        return ParsedResult(
            success=success,
            summary=summary,
            notes=notes,
            touched_paths=suspected_paths,
            retryable_error=aider_error_detected,
        )

    def should_retry(
        self,
        stdout: str,
        stderr: str,
        exit_code: int,
    ) -> bool:
        """Determine if Aider execution should be retried.

        Args:
            stdout: Standard output from execution.
            stderr: Standard error from execution.
            exit_code: Exit code from execution.

        Returns:
            True if the error is retryable (aider-specific error), False otherwise.
        """
        result = self.parse_output(stdout, stderr, exit_code)
        return result.retryable_error

    def get_timeout(self, task_type: str) -> int:
        """Get timeout for Aider based on task type.

        Args:
            task_type: Type of task ('quick', 'sequential', 'parallel').

        Returns:
            Timeout in seconds.
        """
        base_timeout = int(os.environ.get("NINJA_AIDER_TIMEOUT", "300"))

        # Parallel tasks may need more time (multiple API calls)
        if task_type == "parallel":
            return base_timeout * 2

        return base_timeout
