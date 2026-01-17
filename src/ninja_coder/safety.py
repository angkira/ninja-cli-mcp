"""
Safety utilities to prevent accidental file overwrites.

This module provides git-based safety checks and recovery mechanisms
to protect against destructive operations.
"""

from __future__ import annotations

import os
import subprocess
from enum import Enum
from pathlib import Path
from typing import Any

from ninja_common.logging_utils import get_logger

logger = get_logger(__name__)


class SafetyMode(str, Enum):
    """Safety enforcement modes."""

    STRICT = "strict"  # Refuse to run with uncommitted changes
    AUTO = "auto"  # Auto-create safety tags/commits before running
    WARN = "warn"  # Warn but allow execution
    OFF = "off"  # Disable safety checks


class GitSafetyChecker:
    """Check git repository safety before executing tasks."""

    @staticmethod
    def is_git_repo(repo_root: str) -> bool:
        """Check if directory is a git repository.

        Args:
            repo_root: Repository root path.

        Returns:
            True if directory is a git repository.
        """
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--git-dir"],
                cwd=repo_root,
                capture_output=True,
                timeout=5,
            )
            return result.returncode == 0
        except Exception:
            return False

    @staticmethod
    def has_uncommitted_changes(repo_root: str) -> tuple[bool, list[str]]:
        """Check for uncommitted changes.

        Args:
            repo_root: Repository root path.

        Returns:
            Tuple of (has_changes, list_of_changed_files).
        """
        try:
            # Check for staged and unstaged changes
            result = subprocess.run(
                ["git", "status", "--short"],
                cwd=repo_root,
                capture_output=True,
                text=True,
                timeout=5,
            )

            if result.returncode != 0:
                return False, []

            output = result.stdout.strip()
            if not output:
                return False, []

            # Parse changed files
            changed_files = []
            for line in output.split("\n"):
                if line.strip():
                    # Format: "XY filename"
                    parts = line.split(maxsplit=1)
                    if len(parts) == 2:
                        changed_files.append(parts[1])

            return True, changed_files

        except Exception as e:
            logger.warning(f"Failed to check git status: {e}")
            return False, []

    @staticmethod
    def create_safety_tag(repo_root: str) -> str | None:
        """Create a git tag for easy recovery.

        Args:
            repo_root: Repository root path.

        Returns:
            Tag name if created, None otherwise.
        """
        try:
            import time

            tag_name = f"ninja-safety-{int(time.time())}"

            result = subprocess.run(
                ["git", "tag", "-f", tag_name],
                cwd=repo_root,
                capture_output=True,
                timeout=5,
            )

            if result.returncode == 0:
                logger.info(f"Created safety tag: {tag_name}")
                return tag_name
            else:
                logger.warning(f"Failed to create safety tag: {result.stderr.decode()}")
                return None

        except Exception as e:
            logger.warning(f"Failed to create safety tag: {e}")
            return None

    @staticmethod
    def auto_commit_changes(repo_root: str, task_description: str = "") -> bool:
        """Automatically commit all changes before running task.

        Args:
            repo_root: Repository root path.
            task_description: Description of the task for commit message.

        Returns:
            True if committed successfully, False otherwise.
        """
        try:
            import time

            # Add all changes
            result = subprocess.run(
                ["git", "add", "."],
                cwd=repo_root,
                capture_output=True,
                timeout=10,
            )

            if result.returncode != 0:
                logger.warning(f"Failed to git add: {result.stderr.decode()}")
                return False

            # Create commit message
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
            task_summary = task_description[:60] + "..." if len(task_description) > 60 else task_description
            commit_msg = f"[ninja-auto-save] Before task: {task_summary}\n\nTimestamp: {timestamp}\nAutomatic safety commit by ninja-coder"

            # Commit changes
            result = subprocess.run(
                ["git", "commit", "-m", commit_msg],
                cwd=repo_root,
                capture_output=True,
                timeout=10,
            )

            if result.returncode == 0:
                logger.info("✅ Auto-committed changes for safety")
                return True
            elif b"nothing to commit" in result.stdout:
                logger.info("No changes to commit")
                return True
            else:
                logger.warning(f"Failed to commit: {result.stderr.decode()}")
                return False

        except Exception as e:
            logger.warning(f"Failed to auto-commit: {e}")
            return False

    @staticmethod
    def get_current_commit(repo_root: str) -> str | None:
        """Get current commit hash.

        Args:
            repo_root: Repository root path.

        Returns:
            Commit hash or None.
        """
        try:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=repo_root,
                capture_output=True,
                text=True,
                timeout=5,
            )

            if result.returncode == 0:
                return result.stdout.strip()
            return None

        except Exception:
            return None

    @classmethod
    def check_safety(
        cls,
        repo_root: str,
        allow_dirty: bool = True,
        create_tag: bool = True,
    ) -> dict[str, Any]:
        """Perform comprehensive safety check.

        Args:
            repo_root: Repository root path.
            allow_dirty: Allow execution with uncommitted changes.
            create_tag: Create safety tag for recovery.

        Returns:
            Safety check results with warnings and recommendations.
        """
        results = {
            "safe": True,
            "warnings": [],
            "commit_hash": None,
            "safety_tag": None,
            "is_git_repo": False,
            "has_changes": False,
            "changed_files": [],
        }

        # Check if git repo
        results["is_git_repo"] = cls.is_git_repo(repo_root)
        if not results["is_git_repo"]:
            results["warnings"].append(
                "⚠️  Not a git repository - cannot track changes or recover from overwrites"
            )
            results["safe"] = False
            return results

        # Get current commit
        results["commit_hash"] = cls.get_current_commit(repo_root)
        if results["commit_hash"]:
            logger.info(f"Current commit: {results['commit_hash'][:8]}")

        # Check for uncommitted changes
        has_changes, changed_files = cls.has_uncommitted_changes(repo_root)
        results["has_changes"] = has_changes
        results["changed_files"] = changed_files

        if has_changes:
            results["warnings"].append(
                f"⚠️  {len(changed_files)} uncommitted file(s) - "
                "consider committing before running tasks"
            )
            if not allow_dirty:
                results["safe"] = False

        # Create safety tag if requested
        if create_tag and results["is_git_repo"]:
            tag = cls.create_safety_tag(repo_root)
            if tag:
                results["safety_tag"] = tag
                results["warnings"].append(
                    f"✅ Safety tag created: {tag} "
                    "(recover with: git reset --hard {tag})"
                )

        return results


def validate_task_safety(
    repo_root: str,
    task_description: str,
    context_paths: list[str] | None = None,
    safety_mode: SafetyMode | str | None = None,
) -> dict[str, Any]:
    """Validate task safety before execution with automatic enforcement.

    Args:
        repo_root: Repository root path.
        task_description: Task description to analyze.
        context_paths: Files that will be modified.
        safety_mode: Safety enforcement mode (auto-detected from env if None).

    Returns:
        Safety validation results with recommendations and enforcement actions.
    """
    # Determine safety mode
    if safety_mode is None:
        mode_str = os.environ.get("NINJA_SAFETY_MODE", "auto").lower()
        try:
            safety_mode = SafetyMode(mode_str)
        except ValueError:
            logger.warning(f"Invalid NINJA_SAFETY_MODE '{mode_str}', using 'auto'")
            safety_mode = SafetyMode.AUTO

    results = {
        "safe": True,
        "warnings": [],
        "recommendations": [],
        "safety_mode": safety_mode.value,
        "action_taken": None,
    }

    # Skip safety checks if mode is OFF
    if safety_mode == SafetyMode.OFF:
        results["warnings"].append("⚠️  Safety checks disabled (NINJA_SAFETY_MODE=off)")
        return results

    # Check git safety (don't create tag yet in strict/auto mode)
    create_tag = safety_mode == SafetyMode.WARN
    git_check = GitSafetyChecker.check_safety(
        repo_root,
        allow_dirty=True,
        create_tag=create_tag,
    )

    results["git_info"] = git_check

    # Handle uncommitted changes based on safety mode
    if git_check["has_changes"]:
        changed_files = git_check.get("changed_files", [])

        if safety_mode == SafetyMode.STRICT:
            # STRICT: Refuse to run
            results["safe"] = False
            results["warnings"].append(
                f"❌ STRICT MODE: Refusing to run with {len(changed_files)} uncommitted file(s)"
            )
            results["recommendations"].append("Commit your changes first: git add . && git commit -m 'message'")
            results["recommendations"].append("Or set NINJA_SAFETY_MODE=auto for automatic commits")
            return results

        elif safety_mode == SafetyMode.AUTO:
            # AUTO: Automatically commit changes
            logger.info(f"🔒 AUTO MODE: Committing {len(changed_files)} uncommitted file(s)")
            committed = GitSafetyChecker.auto_commit_changes(repo_root, task_description)

            if committed:
                results["action_taken"] = "auto_committed"
                results["warnings"].append(
                    f"✅ Auto-committed {len(changed_files)} file(s) for safety"
                )
                # Create safety tag after commit
                tag = GitSafetyChecker.create_safety_tag(repo_root)
                if tag:
                    results["git_info"]["safety_tag"] = tag
                    results["warnings"].append(
                        f"✅ Safety tag created: {tag} (recover with: git reset --hard {tag})"
                    )
            else:
                results["safe"] = False
                results["warnings"].append(
                    "❌ Failed to auto-commit changes - cannot proceed safely"
                )
                results["recommendations"].append("Commit manually: git add . && git commit -m 'message'")
                return results

        else:  # WARN mode
            # WARN: Just log warnings
            results["warnings"].extend(git_check["warnings"])

    else:
        # No uncommitted changes - create safety tag
        tag = GitSafetyChecker.create_safety_tag(repo_root)
        if tag:
            results["git_info"]["safety_tag"] = tag
            results["warnings"].append(
                f"✅ Safety tag created: {tag} (recover with: git reset --hard {tag})"
            )

    # Check for dangerous keywords in task description
    dangerous_keywords = [
        "rewrite",
        "replace entire",
        "start from scratch",
        "delete everything",
        "remove all",
    ]

    task_lower = task_description.lower()
    for keyword in dangerous_keywords:
        if keyword in task_lower:
            results["warnings"].append(
                f"⚠️  Task contains potentially destructive keyword: '{keyword}'"
            )
            results["recommendations"].append(
                "Consider using more specific edit instructions instead of full rewrites"
            )

    # Check if context paths provided
    if not context_paths or len(context_paths) == 0:
        results["warnings"].append(
            "⚠️  No context_paths provided - AI may not understand which files to edit"
        )
        results["recommendations"].append(
            "Add context_paths parameter with files to edit for better results"
        )

    # Check for vague instructions
    vague_keywords = [
        "update",
        "fix",
        "improve",
        "refactor",
    ]

    vague_count = sum(1 for kw in vague_keywords if kw in task_lower)
    if vague_count >= 2 and len(task_description.split()) < 20:
        results["warnings"].append(
            "⚠️  Task description seems vague - be more specific to avoid rewrites"
        )
        results["recommendations"].append(
            "Provide specific line numbers, method names, or detailed instructions"
        )

    return results
