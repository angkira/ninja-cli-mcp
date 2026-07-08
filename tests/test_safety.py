"""Tests for ninja_coder.safety module.

Covers GitSafetyChecker and validate_task_safety with real git repos.
"""

from __future__ import annotations

import stat
import subprocess
from typing import TYPE_CHECKING

import pytest


if TYPE_CHECKING:
    from pathlib import Path

from ninja_coder.safety import GitSafetyChecker, SafetyMode, validate_task_safety


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    """Initialized git repo with a configured identity and one initial commit."""
    repo = tmp_path / "repo"
    repo.mkdir()

    def _git(*args: str) -> None:
        subprocess.run(["git", *args], cwd=repo, capture_output=True, check=True)

    _git("init")
    _git("config", "user.name", "Test User")
    _git("config", "user.email", "test@test.com")

    (repo / "README.md").write_text("# Test\n")
    _git("add", "README.md")
    _git("commit", "-m", "initial commit")

    return repo


# ---------------------------------------------------------------------------
# has_uncommitted_changes — rename path parsing
# ---------------------------------------------------------------------------


def test_has_uncommitted_changes_rename_returns_new_path(git_repo: Path) -> None:
    """After git mv, has_uncommitted_changes must report the NEW path, not 'old -> new'."""
    subprocess.run(
        ["git", "mv", "README.md", "README_new.md"],
        cwd=git_repo,
        capture_output=True,
        check=True,
    )

    has_changes, changed_files = GitSafetyChecker.has_uncommitted_changes(str(git_repo))

    assert has_changes is True
    for path in changed_files:
        assert " -> " not in path, f"Path contains rename arrow: {path!r}"
    assert any("README_new.md" in p for p in changed_files), (
        f"Expected 'README_new.md' in changed_files, got: {changed_files}"
    )


# ---------------------------------------------------------------------------
# auto_commit_changes — per-change-type success
# ---------------------------------------------------------------------------


def test_auto_commit_new_untracked_file(git_repo: Path) -> None:
    """auto_commit_changes returns True and creates a commit for a new untracked file."""
    (git_repo / "new_file.py").write_text("# new\n")

    result = GitSafetyChecker.auto_commit_changes(str(git_repo), "add new_file.py")

    assert result is True
    log = subprocess.run(
        ["git", "log", "--oneline", "-1"],
        cwd=git_repo,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "ninja-auto-save" in log.stdout


def test_auto_commit_modified_tracked_file(git_repo: Path) -> None:
    """auto_commit_changes returns True and creates a commit for a modified tracked file."""
    (git_repo / "README.md").write_text("# Modified\n")

    result = GitSafetyChecker.auto_commit_changes(str(git_repo), "modify README")

    assert result is True
    log = subprocess.run(
        ["git", "log", "--oneline", "-1"],
        cwd=git_repo,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "ninja-auto-save" in log.stdout


def test_auto_commit_renamed_file(git_repo: Path) -> None:
    """auto_commit_changes returns True and creates a commit after git mv."""
    subprocess.run(
        ["git", "mv", "README.md", "README_renamed.md"],
        cwd=git_repo,
        capture_output=True,
        check=True,
    )

    result = GitSafetyChecker.auto_commit_changes(str(git_repo), "rename README")

    assert result is True
    log = subprocess.run(
        ["git", "log", "--oneline", "-1"],
        cwd=git_repo,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "ninja-auto-save" in log.stdout


def test_auto_commit_deleted_file(git_repo: Path) -> None:
    """auto_commit_changes returns True and creates a commit for a deleted tracked file."""
    subprocess.run(
        ["git", "rm", "README.md"],
        cwd=git_repo,
        capture_output=True,
        check=True,
    )

    result = GitSafetyChecker.auto_commit_changes(str(git_repo), "delete README")

    assert result is True
    log = subprocess.run(
        ["git", "log", "--oneline", "-1"],
        cwd=git_repo,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "ninja-auto-save" in log.stdout


# ---------------------------------------------------------------------------
# auto_commit_changes — identity fallback
# ---------------------------------------------------------------------------


def test_auto_commit_no_identity_uses_fallback(
    git_repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """auto_commit_changes injects a fallback identity when none is configured."""
    # Remove local identity that the fixture set
    subprocess.run(
        ["git", "config", "--local", "--unset", "user.name"],
        cwd=git_repo,
        capture_output=True,
        check=True,
    )
    subprocess.run(
        ["git", "config", "--local", "--unset", "user.email"],
        cwd=git_repo,
        capture_output=True,
        check=True,
    )

    # Point HOME at an empty temp dir so ~/.gitconfig cannot be found
    fake_home = tmp_path / "home"
    fake_home.mkdir(exist_ok=True)
    monkeypatch.setenv("HOME", str(fake_home))
    # Prevent reading the system-wide git config
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")

    (git_repo / "new_file.py").write_text("# new\n")

    result = GitSafetyChecker.auto_commit_changes(str(git_repo), "no identity test")

    assert result is True, "auto_commit_changes must succeed even without a configured identity"
    log = subprocess.run(
        ["git", "log", "--oneline", "-1"],
        cwd=git_repo,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "ninja-auto-save" in log.stdout


# ---------------------------------------------------------------------------
# auto_commit_changes — pre-commit hook bypass
# ---------------------------------------------------------------------------


def test_auto_commit_bypasses_failing_pre_commit_hook(git_repo: Path) -> None:
    """auto_commit_changes succeeds even when a pre-commit hook exits 1 (--no-verify)."""
    hook = git_repo / ".git" / "hooks" / "pre-commit"
    hook.write_text("#!/bin/sh\nexit 1\n")
    hook.chmod(hook.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    (git_repo / "new_file.py").write_text("# new\n")

    result = GitSafetyChecker.auto_commit_changes(str(git_repo), "hook bypass test")

    assert result is True, "auto_commit_changes must bypass failing pre-commit hooks via --no-verify"
    log = subprocess.run(
        ["git", "log", "--oneline", "-1"],
        cwd=git_repo,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "ninja-auto-save" in log.stdout


# ---------------------------------------------------------------------------
# validate_task_safety — AUTO mode on a dirty repo
# ---------------------------------------------------------------------------


def test_validate_task_safety_auto_dirty_repo_commits_and_tags(git_repo: Path) -> None:
    """AUTO mode on a dirty repo: safe=True, action_taken=='auto_committed', safety_tag set."""
    (git_repo / "dirty.py").write_text("# dirty\n")

    results = validate_task_safety(
        repo_root=str(git_repo),
        task_description="test task",
        safety_mode=SafetyMode.AUTO,
    )

    assert results["safe"] is True
    assert results["action_taken"] == "auto_committed"
    git_info = results.get("git_info", {})
    assert git_info.get("safety_tag") is not None, (
        "A safety tag must be created after a successful auto-commit"
    )


# ---------------------------------------------------------------------------
# validate_task_safety — STRICT deprecation
# ---------------------------------------------------------------------------


def test_validate_task_safety_strict_env_does_not_deny(
    git_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """NINJA_SAFETY_MODE=strict must not deny the task — it maps to AUTO."""
    monkeypatch.setenv("NINJA_SAFETY_MODE", "strict")
    (git_repo / "dirty.py").write_text("# dirty\n")

    results = validate_task_safety(
        repo_root=str(git_repo),
        task_description="test task",
        safety_mode=None,  # read from env
    )

    assert results["safe"] is True, (
        "STRICT mode is deprecated; a dirty worktree must never block task execution"
    )


# ---------------------------------------------------------------------------
# validate_task_safety — OFF mode short-circuits
# ---------------------------------------------------------------------------


def test_validate_task_safety_off_no_commit_created(
    git_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """NINJA_SAFETY_MODE=off returns safe=True and creates no git commits."""
    monkeypatch.setenv("NINJA_SAFETY_MODE", "off")
    (git_repo / "dirty.py").write_text("# dirty\n")

    log_before = subprocess.run(
        ["git", "log", "--oneline"],
        cwd=git_repo,
        capture_output=True,
        text=True,
        check=True,
    )
    commit_count_before = len(log_before.stdout.strip().split("\n"))

    results = validate_task_safety(
        repo_root=str(git_repo),
        task_description="test task",
        safety_mode=None,  # read from env
    )

    assert results["safe"] is True

    log_after = subprocess.run(
        ["git", "log", "--oneline"],
        cwd=git_repo,
        capture_output=True,
        text=True,
        check=True,
    )
    commit_count_after = len(log_after.stdout.strip().split("\n"))
    assert commit_count_after == commit_count_before, (
        "NINJA_SAFETY_MODE=off must not create any git commits"
    )
