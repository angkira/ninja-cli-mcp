"""
Safety utilities to prevent accidental file overwrites.

This module provides git-based safety checks and recovery mechanisms
to protect against destructive operations.
"""

from __future__ import annotations

import os
import subprocess
from enum import Enum
from typing import Any

from ninja_common.logging_utils import get_logger


logger = get_logger(__name__)


class SafetyMode(str, Enum):
    """Safety enforcement modes.

    STRICT has been removed. Any NINJA_SAFETY_MODE=strict configuration is
    treated as AUTO with a deprecation warning — tasks are never denied due
    to a dirty worktree.
    """

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
                check=False,
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
                check=False,
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
                    # Status code occupies the first 2 chars; path follows after a space
                    path = line[2:].strip()
                    # Rename/copy entries contain " -> "; keep only the destination path
                    if " -> " in path:
                        path = path.split(" -> ", 1)[1]
                    # Strip quotes that git adds for paths with special characters
                    path = path.strip().strip('"')
                    if path:
                        changed_files.append(path)

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
                check=False,
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
    def auto_commit_changes(
        repo_root: str, task_description: str = "", changed_files: list[str] | None = None
    ) -> bool:
        """Automatically commit all changes before running task.

        Args:
            repo_root: Repository root path.
            task_description: Description of task for commit message.
            changed_files: Advisory; provided for context but staging always uses
                ``git add -A`` so renames and deletions are handled correctly.

        Returns:
            True if committed successfully, False otherwise.
        """
        try:
            import time

            # Stage all changes atomically — avoids per-file add failures for renames etc.
            add_result = subprocess.run(
                ["git", "add", "-A"],
                cwd=repo_root,
                capture_output=True,
                timeout=10,
                check=False,
            )
            if add_result.returncode != 0:
                logger.warning(f"Failed to git add -A: {add_result.stderr.decode()}")
                return False

            # Create commit message
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
            task_summary = (
                task_description[:60] + "..." if len(task_description) > 60 else task_description
            )
            file_hint = f"\nFiles detected: {len(changed_files)}" if changed_files else ""
            commit_msg = f"[ninja-auto-save] Before task: {task_summary}\n\nTimestamp: {timestamp}{file_hint}\nAutomatic safety commit by ninja-coder"

            # Detect whether git identity is configured; inject a fallback if not
            name_result = subprocess.run(
                ["git", "config", "user.name"],
                cwd=repo_root,
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            email_result = subprocess.run(
                ["git", "config", "user.email"],
                cwd=repo_root,
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )

            has_identity = (
                name_result.returncode == 0
                and bool(name_result.stdout.strip())
                and email_result.returncode == 0
                and bool(email_result.stdout.strip())
            )

            identity_args: list[str] = []
            if not has_identity:
                logger.warning("Git identity not configured; using fallback ninja-coder identity")
                identity_args = [
                    "-c", "user.name=ninja-coder",
                    "-c", "user.email=ninja@localhost",
                ]

            commit_cmd = [
                "git",
                *identity_args,
                "commit",
                "--no-verify",
                "--no-gpg-sign",
                "-m",
                commit_msg,
            ]

            # Commit changes, bypassing hooks and signing requirements
            result = subprocess.run(
                commit_cmd,
                cwd=repo_root,
                capture_output=True,
                timeout=10,
                check=False,
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
                check=False,
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
                    f"✅ Safety tag created: {tag} (recover with: git reset --hard {{tag}})"
                )

        return results


def validate_task_safety(
    repo_root: str,
    task_description: str,
    context_paths: list[str] | None = None,
    safety_mode: SafetyMode | str | None = None,
    skip_auto_commit: bool = False,
) -> dict[str, Any]:
    """Validate task safety before execution with automatic enforcement.

    Args:
        repo_root: Repository root path.
        task_description: Task description to analyze.
        context_paths: Files that will be modified.
        safety_mode: Safety enforcement mode (auto-detected from env if None).
        skip_auto_commit: When True, AUTO mode never creates the
            [ninja-auto-save] commit on the current branch (used when
            worktree isolation snapshots the dirty state onto a feature
            branch instead). The safety tag on HEAD is still created.

    Returns:
        Safety validation results with recommendations and enforcement actions.
    """
    # Determine safety mode
    if safety_mode is None:
        mode_str = os.environ.get("NINJA_SAFETY_MODE", "auto").lower()
        if mode_str == "strict":
            logger.warning(
                "NINJA_SAFETY_MODE=strict is deprecated and now behaves as 'auto' (never denies)"
            )
            safety_mode = SafetyMode.AUTO
        else:
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

    # Check git safety (don't create tag yet in auto mode; WARN creates tag upfront)
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

        if safety_mode == SafetyMode.AUTO:
            if skip_auto_commit:
                # Worktree isolation is active: the dirty state is snapshotted
                # onto a feature branch in a detached worktree, so the main
                # repo must NOT get an auto-save commit. Only tag HEAD.
                logger.info(
                    f"🔀 AUTO MODE: worktree isolation active, leaving "
                    f"{len(changed_files)} uncommitted file(s) untouched"
                )
                results["action_taken"] = "worktree_isolation"
                results["warnings"].append(
                    f"🔀 Worktree isolation: {len(changed_files)} uncommitted file(s) "
                    "preserved in the main working tree (snapshot on feature branch)"
                )
                tag = GitSafetyChecker.create_safety_tag(repo_root)
                if tag:
                    results["git_info"]["safety_tag"] = tag
                    results["warnings"].append(
                        f"✅ Safety tag created: {tag} (recover with: git reset --hard {tag})"
                    )
            else:
                # AUTO: Automatically commit changes; never deny the task
                logger.info(f"🔒 AUTO MODE: Committing {len(changed_files)} uncommitted file(s)")
                committed = GitSafetyChecker.auto_commit_changes(
                    repo_root, task_description, changed_files
                )

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
                    results["warnings"].append(
                        "⚠️ Could not create safety commit — proceeding without a git recovery point"
                    )
                    # safe stays True — never deny a task due to a dirty worktree

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
