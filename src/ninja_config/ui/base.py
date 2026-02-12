"""Shared UI utilities and helper functions.

This module provides reusable UI components and utility functions used across
the interactive configurator. All functions are stateless and use dependency injection.
"""

import shutil
import subprocess
from pathlib import Path

try:
    from InquirerPy import inquirer
    from InquirerPy.base.control import Choice
    from InquirerPy.separator import Separator

    HAS_INQUIRERPY = True
except ImportError:
    HAS_INQUIRERPY = False


def get_masked_value(value: str) -> str:
    """Return masked version of sensitive value.

    Args:
        value: The value to mask (e.g., API key)

    Returns:
        Masked string showing first 4 and last 4 characters, or "*** NOT SET ***"
    """
    if not value or len(value) < 8:
        return "*** NOT SET ***"
    return f"{value[:4]}...{value[-4:]}"


def print_header(title: str, width: int = 80) -> None:
    """Print a formatted header with decorations.

    Args:
        title: The header title text
        width: Total width of the header line (default: 80)
    """
    print("\n" + "=" * width)
    print(f"  {title}")
    print("=" * width)


def detect_installed_tools() -> dict[str, str]:
    """Detect installed AI coding tools.

    Searches for common AI coding assistants in the system PATH.

    Returns:
        Dictionary mapping tool name to its binary path
        Example: {"aider": "/usr/local/bin/aider", "opencode": "/usr/bin/opencode"}
    """
    tools = {}

    # Check for aider
    if shutil.which("aider"):
        tools["aider"] = shutil.which("aider")

    # Check for opencode
    if shutil.which("opencode"):
        tools["opencode"] = shutil.which("opencode")

    # Check for gemini
    if shutil.which("gemini"):
        tools["gemini"] = shutil.which("gemini")

    # Check for claude (Claude Code)
    if shutil.which("claude"):
        tools["claude"] = shutil.which("claude")

    # Check for cursor
    if shutil.which("cursor"):
        tools["cursor"] = shutil.which("cursor")

    return tools


def check_opencode_auth() -> list[str]:
    """Check OpenCode authentication status.

    Runs `opencode auth list` to determine which providers are authenticated.

    Returns:
        List of authenticated provider names (e.g., ["anthropic", "google"])
    """
    if not shutil.which("opencode"):
        return []

    try:
        result = subprocess.run(
            ["opencode", "auth", "list"],
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
        if result.returncode == 0:
            # Parse output to find authenticated providers
            providers = []
            output = result.stdout.lower()
            if "anthropic" in output:
                providers.append("anthropic")
            if "google" in output or "gemini" in output:
                providers.append("google")
            if "openai" in output:
                providers.append("openai")
            if "github" in output:
                providers.append("github")
            if "zai" in output or "zhipu" in output:
                providers.append("zai")
            return providers
    except Exception:
        pass

    return []
