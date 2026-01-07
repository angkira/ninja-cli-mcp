"""Base utilities for Claude Code hook commands."""

from __future__ import annotations

import json
import subprocess
import sys
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class HookResult:
    """Standard result format for hook commands."""

    status: str  # ok, pass, fail, error, valid, invalid, formatted, unchanged
    message: str | None = None
    data: dict[str, Any] = field(default_factory=dict)

    @property
    def success(self) -> bool:
        """Check if result indicates success."""
        return self.status in ("ok", "pass", "valid", "formatted", "unchanged")


class HookCommand(ABC):
    """Abstract base class for hook commands."""

    def __init__(self, json_output: bool = False):
        self.json_output = json_output

    @abstractmethod
    def execute(self) -> HookResult:
        """Execute the hook command and return result."""
        pass

    def run(self) -> int:
        """Run command and handle output. Returns exit code."""

        try:
            result = self.execute()
            output = {"status": result.status, "message": result.message, **result.data}

            if self.json_output:
                print(json.dumps(output, indent=2))
            else:
                self._print_human_readable(result)

            return 0 if result.success else 1

        except Exception as e:
            error_output = {"status": "error", "message": str(e)}
            if self.json_output:
                print(json.dumps(error_output, indent=2))
            else:
                print(f"Error: {e}", file=sys.stderr)
            return 1

    def _print_human_readable(self, result: HookResult) -> None:
        """Print human-readable output. Override in subclasses."""
        if result.message:
            print(result.message)
        for key, value in result.data.items():
            print(f"{key}: {value}")


def run_subprocess(
    cmd: list[str],
    cwd: str | Path | None = None,
    timeout: float = 30.0,
    capture_output: bool = True,
) -> tuple[int, str, str]:
    """
    Run a subprocess with timeout.

    Returns:
        Tuple of (exit_code, stdout, stderr)
    """
    try:
        result = subprocess.run(
            cmd,
            check=False,
            cwd=cwd,
            timeout=timeout,
            capture_output=capture_output,
            text=True,
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return -1, "", f"Command timed out after {timeout}s"
    except FileNotFoundError:
        return -1, "", f"Command not found: {cmd[0]}"


def detect_file_type(file_path: str | Path) -> str:
    """
    Detect file type from extension.

    Returns one of: python, javascript, typescript, rust, go, json, yaml, markdown, unknown
    """
    ext_map = {
        ".py": "python",
        ".pyi": "python",
        ".js": "javascript",
        ".jsx": "javascript",
        ".mjs": "javascript",
        ".ts": "typescript",
        ".tsx": "typescript",
        ".rs": "rust",
        ".go": "go",
        ".json": "json",
        ".yaml": "yaml",
        ".yml": "yaml",
        ".md": "markdown",
        ".markdown": "markdown",
    }

    suffix = Path(file_path).suffix.lower()
    return ext_map.get(suffix, "unknown")


def get_repo_root(start_path: str | Path | None = None) -> Path | None:
    """
    Find git repository root from start_path or current directory.

    Returns:
        Path to repo root, or None if not in a git repository.
    """
    try:
        start = Path(start_path) if start_path else Path.cwd()
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            check=False,
            cwd=start,
            capture_output=True,
            text=True,
            timeout=5.0,
        )
        if result.returncode == 0:
            return Path(result.stdout.strip())
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return None


def get_staged_files(repo_root: str | Path | None = None) -> list[str]:
    """
    Get list of staged files in git.

    Returns:
        List of staged file paths relative to repo root.
    """
    try:
        result = subprocess.run(
            ["git", "diff", "--cached", "--name-only"],
            check=False,
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=5.0,
        )
        if result.returncode == 0:
            return [f for f in result.stdout.strip().split("\n") if f]
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return []
