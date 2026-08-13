"""Tests for ninja_coder.worktree module and its driver integration.

Covers WorktreeManager with real git repos (following tests/test_safety.py
patterns) and the execute_async integration with a mocked CLI subprocess.
"""

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest


if TYPE_CHECKING:
    from pathlib import Path

from ninja_coder.driver import NinjaConfig, NinjaDriver
from ninja_coder.safety import SafetyMode, validate_task_safety
from ninja_coder.worktree import (
    SNAPSHOT_EXCLUDED_DIRS,
    WORKTREE_MAX_AGE_ENV,
    WORKTREE_MODE_ENV,
    WorktreeManager,
)


# ---------------------------------------------------------------------------
# Fixtures / helpers
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
    (repo / ".gitignore").write_text("ignored.log\n")
    _git("add", "README.md", ".gitignore")
    _git("commit", "-m", "initial commit")

    return repo


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """Run a git command in repo and return the completed process."""
    return subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True, check=True
    )


def _make_dirty(repo: Path) -> None:
    """Add a tracked modification, an untracked file and an ignored file."""
    (repo / "README.md").write_text("# Modified\n")
    (repo / "untracked.py").write_text("# new\n")
    (repo / "ignored.log").write_text("noise\n")


# ---------------------------------------------------------------------------
# WorktreeManager.create — dirty repo isolation
# ---------------------------------------------------------------------------


def test_create_dirty_repo_snapshots_and_leaves_main_untouched(
    git_repo: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Dirty main tree: snapshot lands on the feature branch, main stays dirty."""
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    _make_dirty(git_repo)

    head_before = _git(git_repo, "rev-parse", "HEAD").stdout.strip()
    branch_before = _git(git_repo, "branch", "--show-current").stdout.strip()
    status_before = _git(git_repo, "status", "--porcelain").stdout

    info = WorktreeManager().create(
        repo_root=str(git_repo), task_hint="test task", step_id="step1"
    )

    assert info is not None
    assert info.path.exists()
    assert info.branch.startswith("ninja/")
    assert len(info.branch) <= 40

    # Branch exists in the repo and is checked out in the worktree
    branches = _git(git_repo, "branch", "--list", info.branch).stdout
    assert info.branch in branches
    wt_branch = _git(info.path, "branch", "--show-current").stdout.strip()
    assert wt_branch == info.branch

    # Snapshot commit on the feature branch contains the dirty changes
    assert info.snapshot_commit is not None
    wt_log = _git(info.path, "log", "-1", "--format=%s").stdout
    assert "ninja-auto-save" in wt_log
    assert (info.path / "README.md").read_text() == "# Modified\n"
    assert (info.path / "untracked.py").read_text() == "# new\n"
    # .gitignore is respected: ignored untracked files are not snapshotted
    assert not (info.path / "ignored.log").exists()

    # MAIN tree: byte-for-byte untouched
    assert _git(git_repo, "rev-parse", "HEAD").stdout.strip() == head_before
    assert _git(git_repo, "branch", "--show-current").stdout.strip() == branch_before
    assert _git(git_repo, "status", "--porcelain").stdout == status_before
    assert (git_repo / "README.md").read_text() == "# Modified\n"
    assert (git_repo / "untracked.py").read_text() == "# new\n"

    # No auto-save commit on the main branch history
    main_log = _git(git_repo, "log", "--format=%s").stdout
    assert "ninja-auto-save" not in main_log


def test_create_clean_repo_creates_worktree_without_snapshot(
    git_repo: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Clean tree: worktree and branch are created, but no snapshot commit."""
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    head_before = _git(git_repo, "rev-parse", "HEAD").stdout.strip()

    info = WorktreeManager().create(repo_root=str(git_repo), step_id="clean1")

    assert info is not None
    assert info.path.exists()
    assert info.snapshot_commit is None
    # Worktree HEAD is the original HEAD (no extra commits)
    assert _git(info.path, "rev-parse", "HEAD").stdout.strip() == head_before
    # Main repo untouched
    assert _git(git_repo, "status", "--porcelain").stdout == ""
    assert _git(git_repo, "rev-parse", "HEAD").stdout.strip() == head_before


def test_create_non_git_dir_returns_none(tmp_path: Path) -> None:
    """Non-git directory: fallback to None, no crash."""
    plain = tmp_path / "plain"
    plain.mkdir()

    assert WorktreeManager().create(repo_root=str(plain), step_id="x") is None


def test_create_repo_without_commits_returns_none(tmp_path: Path) -> None:
    """Repo with no commits (missing HEAD): fallback to None, no crash."""
    repo = tmp_path / "empty"
    repo.mkdir()
    _git(repo, "init")

    assert WorktreeManager().create(repo_root=str(repo), step_id="x") is None


def test_worktree_mode_off_disables_isolation(monkeypatch: pytest.MonkeyPatch) -> None:
    """NINJA_WORKTREE_MODE=off disables worktree isolation."""
    monkeypatch.setenv(WORKTREE_MODE_ENV, "off")
    assert WorktreeManager.is_enabled() is False

    monkeypatch.setenv(WORKTREE_MODE_ENV, "on")
    assert WorktreeManager.is_enabled() is True


# ---------------------------------------------------------------------------
# Auto-pruning + snapshot exclusions (cache bloat guards)
# ---------------------------------------------------------------------------


def test_max_age_days_default_and_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """_max_age_days() honours NINJA_WORKTREE_MAX_AGE_DAYS."""
    monkeypatch.delenv(WORKTREE_MAX_AGE_ENV, raising=False)
    assert WorktreeManager._max_age_days() == 2

    monkeypatch.setenv(WORKTREE_MAX_AGE_ENV, "0")
    assert WorktreeManager._max_age_days() == 0

    monkeypatch.setenv(WORKTREE_MAX_AGE_ENV, "not-a-number")
    assert WorktreeManager._max_age_days() == 2


def test_prune_removes_old_worktrees_and_keeps_recent(
    git_repo: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """prune() drops worktrees older than the threshold, keeps recent ones."""
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    monkeypatch.setenv(WORKTREE_MAX_AGE_ENV, "0")  # everything older than now

    info = WorktreeManager().create(repo_root=str(git_repo), step_id="prune1")
    assert info is not None and info.path.exists()

    removed = WorktreeManager().prune()
    # With threshold 0 (cutoff = now), the just-created worktree is already old
    assert removed == 1
    assert not info.path.exists()

    # repo_dir is removed once empty
    assert not info.path.parent.exists()


def test_prune_respects_recent_mtime(
    git_repo: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Recent worktrees survive pruning (fresh mtime beats threshold)."""
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    monkeypatch.setenv(WORKTREE_MAX_AGE_ENV, "2")

    info = WorktreeManager().create(repo_root=str(git_repo), step_id="fresh1")
    assert info is not None and info.path.exists()

    removed = WorktreeManager().prune(max_age_days=2)
    assert removed == 0
    assert info.path.exists()


def test_snapshot_excludes_heavy_dirs(
    git_repo: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Heavy/transient dirs (node_modules, .venv, dist) are NOT snapshotted."""
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))

    # Untracked heavy dirs (not covered by .gitignore)
    (git_repo / "node_modules").mkdir()
    (git_repo / "node_modules" / "dep.js").write_text("// big\n")
    (git_repo / ".venv").mkdir()
    (git_repo / ".venv" / "bin").mkdir()
    (git_repo / ".venv" / "bin" / "python").write_text("# venv\n")
    (git_repo / "normal.py").write_text("# keep me\n")

    info = WorktreeManager().create(repo_root=str(git_repo), step_id="heavy1")
    assert info is not None

    assert (info.path / "normal.py").exists()
    assert not (info.path / "node_modules").exists()
    assert not (info.path / ".venv").exists()
    # Heavy dirs are covered by the exclusion list
    assert "node_modules" in SNAPSHOT_EXCLUDED_DIRS
    assert ".venv" in SNAPSHOT_EXCLUDED_DIRS


# ---------------------------------------------------------------------------
# validate_task_safety — skip_auto_commit
# ---------------------------------------------------------------------------


def test_validate_task_safety_skip_auto_commit_preserves_dirty_state(
    git_repo: Path,
) -> None:
    """skip_auto_commit=True: AUTO mode creates no commit, leaves main dirty."""
    _make_dirty(git_repo)
    head_before = _git(git_repo, "rev-parse", "HEAD").stdout.strip()
    status_before = _git(git_repo, "status", "--porcelain").stdout

    results = validate_task_safety(
        repo_root=str(git_repo),
        task_description="test task",
        safety_mode=SafetyMode.AUTO,
        skip_auto_commit=True,
    )

    assert results["safe"] is True
    assert results["action_taken"] == "worktree_isolation"
    assert results["git_info"].get("safety_tag") is not None
    assert _git(git_repo, "rev-parse", "HEAD").stdout.strip() == head_before
    assert _git(git_repo, "status", "--porcelain").stdout == status_before
    main_log = _git(git_repo, "log", "--format=%s").stdout
    assert "ninja-auto-save" not in main_log


# ---------------------------------------------------------------------------
# Driver integration — execute_async with mocked CLI subprocess
# ---------------------------------------------------------------------------


def _build_driver() -> NinjaDriver:
    """Create a driver whose strategy can build a command without a real CLI."""
    config = NinjaConfig(
        bin_path="aider",
        openai_api_key="test-key",
        model="test-model",
        timeout_sec=60,
    )
    return NinjaDriver(config)


def _mock_cli(monkeypatch: pytest.MonkeyPatch, captured: dict[str, str]) -> None:
    """Mock the CLI subprocess and the driver's stream reader."""

    async def mock_subprocess(*args: object, **kwargs: object) -> MagicMock:
        captured["cwd"] = str(kwargs.get("cwd"))
        process = MagicMock()
        process.returncode = 0
        return process

    async def mock_stream(
        self: NinjaDriver,
        process: object,
        max_timeout: float,
        inactivity_timeout: float = 60.0,
        cpu_check_threshold: float = 1.0,
    ) -> tuple[str, str]:
        return "Applied edit to README.md\n", ""

    monkeypatch.setattr("asyncio.create_subprocess_exec", mock_subprocess)
    monkeypatch.setattr(NinjaDriver, "_stream_with_activity_timeout", mock_stream)


@pytest.mark.asyncio
async def test_execute_async_runs_in_worktree_and_leaves_main_untouched(
    git_repo: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """execute_async: subprocess cwd is the worktree; main repo is untouched."""
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    monkeypatch.delenv(WORKTREE_MODE_ENV, raising=False)
    _make_dirty(git_repo)
    head_before = _git(git_repo, "rev-parse", "HEAD").stdout.strip()
    status_before = _git(git_repo, "status", "--porcelain").stdout

    captured: dict[str, str] = {}
    _mock_cli(monkeypatch, captured)

    driver = _build_driver()
    result = await driver.execute_async(
        repo_root=str(git_repo),
        step_id="test_step",
        instruction={
            "task": "Modify the README",
            "file_scope": {"context_paths": ["README.md"]},
        },
        task_type="quick",
    )

    assert result.success is True
    # Worktree info surfaced on the result with a merge hint
    assert result.worktree_branch is not None
    assert result.worktree_branch.startswith("ninja/")
    assert result.worktree_path is not None
    assert result.worktree_path != str(git_repo)
    assert result.worktree_branch in result.notes
    assert "git merge" in result.notes

    # The CLI subprocess ran with cwd=<worktree>
    assert captured["cwd"] == result.worktree_path

    # Main repo untouched: same HEAD, same dirty state, no auto-save commit
    assert _git(git_repo, "rev-parse", "HEAD").stdout.strip() == head_before
    assert _git(git_repo, "status", "--porcelain").stdout == status_before
    main_log = _git(git_repo, "log", "--format=%s").stdout
    assert "ninja-auto-save" not in main_log


@pytest.mark.asyncio
async def test_execute_async_worktree_mode_off_uses_legacy_auto_commit(
    git_repo: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """NINJA_WORKTREE_MODE=off: legacy path — auto-commit on the current branch."""
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    monkeypatch.setenv(WORKTREE_MODE_ENV, "off")
    _make_dirty(git_repo)

    captured: dict[str, str] = {}
    _mock_cli(monkeypatch, captured)

    driver = _build_driver()
    result = await driver.execute_async(
        repo_root=str(git_repo),
        step_id="test_step_off",
        instruction={
            "task": "Modify the README",
            "file_scope": {"context_paths": ["README.md"]},
        },
        task_type="quick",
    )

    assert result.success is True
    assert result.worktree_branch is None
    assert result.worktree_path is None

    # Legacy behavior: subprocess ran in the main repo and the dirty state
    # was auto-committed on the current branch
    assert captured["cwd"] == str(git_repo)
    main_log = _git(git_repo, "log", "-1", "--format=%s").stdout
    assert "ninja-auto-save" in main_log
    assert _git(git_repo, "status", "--porcelain").stdout == ""


@pytest.mark.asyncio
async def test_execute_async_non_git_repo_falls_back(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Non-git repo: no worktree, subprocess runs in repo_root, no crash."""
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    monkeypatch.delenv(WORKTREE_MODE_ENV, raising=False)
    plain = tmp_path / "plain"
    plain.mkdir()

    captured: dict[str, str] = {}
    _mock_cli(monkeypatch, captured)

    driver = _build_driver()
    result = await driver.execute_async(
        repo_root=str(plain),
        step_id="test_step_nogit",
        instruction={"task": "Do something", "file_scope": {"context_paths": []}},
        task_type="quick",
    )

    assert result.success is True
    assert result.worktree_branch is None
    assert captured["cwd"] == str(plain)
