"""
Worktree-based task isolation for the ninja-coder driver.

For each task execution in a git repository, a feature branch
``ninja/<slug>-<timestamp>-<uid>`` is created at the current HEAD and checked
out into a detached git worktree OUTSIDE the repository (under
``$XDG_CACHE_HOME/ninja-mcp/worktrees/<repo-hash>/<branch>``). Uncommitted
changes from the main working tree are snapshotted into the worktree and
committed on the feature branch with the ``[ninja-auto-save]`` message format.
The AI CLI subprocess then runs with ``cwd=<worktree>`` so the user's main
working tree and current branch stay byte-for-byte untouched.

Design decisions:
- Snapshot mechanism: ``git diff HEAD --binary`` piped to ``git apply`` for
  tracked modifications; untracked files (from ``git status --porcelain``,
  which respects .gitignore) are copied with shutil.
- One worktree per ``NinjaDriver.execute_async`` call. Sequential/parallel
  plans execute all steps in ONE execute_async call (single-process mode in
  tools.py), so plan steps naturally share one worktree and branch.
- On completion nothing is merged or removed automatically; the result
  carries the branch name, worktree path and a merge hint.

Limitations (deliberate, to keep the change minimal):
- ``execute_sync`` never creates worktrees (it also never ran safety checks).
- ``execute_async_with_opencode_session`` keeps legacy behavior; session
  continuity across steps conflicts with per-call worktrees.
- The opencode serve-pool path (NINJA_OPENCODE_SERVE_MODE=1) keeps legacy
  behavior; the long-running server is rooted at the user's repo_root.
- ``NINJA_WORKTREE_MODE=off`` disables isolation entirely and preserves the
  legacy AUTO-mode behavior (auto-commit on the user's current branch).
- ``prune()`` is a manual helper; nothing calls it automatically.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

from ninja_coder.safety import GitSafetyChecker
from ninja_common.logging_utils import get_logger
from ninja_common.path_utils import get_cache_dir


logger = get_logger(__name__)

#: Environment variable that disables worktree isolation when set to "off".
WORKTREE_MODE_ENV = "NINJA_WORKTREE_MODE"

#: Prefix for feature branches created for task isolation.
_BRANCH_PREFIX = "ninja/"

#: Max length of the sanitized slug segment of a branch name. Keeps the full
#: branch name (prefix + slug + timestamp + unique suffix) at <= 40 chars.
_MAX_SLUG_LEN = 16

#: Length of the random suffix that makes branch names unique per execution.
_UNIQUE_SUFFIX_LEN = 6

#: Characters of the sha256 repo-path hash used for the worktree base dir.
#: Matches the cache-key style of ninja_common.path_utils.get_internal_dir.
_REPO_HASH_LEN = 16

#: Timeout for all git subprocess calls (consistent with safety.py: 5-15s).
_GIT_TIMEOUT_SEC = 15

#: Seconds per day, used by prune() to convert max_age_days to a cutoff.
_SECONDS_PER_DAY = 86_400

#: Default age threshold for prune() (overridable via NINJA_WORKTREE_MAX_AGE_DAYS).
_DEFAULT_MAX_AGE_DAYS = 2

#: Env var to tune the automatic worktree pruning age (in days).
WORKTREE_MAX_AGE_ENV = "NINJA_WORKTREE_MAX_AGE_DAYS"

#: Heavy/build/transient paths NEVER copied into a snapshot worktree. Guards
#: against node_modules and friends blowing up the cache when they are not
#: covered by the repo's .gitignore.
SNAPSHOT_EXCLUDED_DIRS = {
    "node_modules",
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "htmlcov",
    ".coverage",
    "dist",
    "build",
    ".cache",
    ".next",
    ".turbo",
    "target",
    ".idea",
    ".vscode",
    ".terraform",
    "vendor",
    "bower_components",
    "coverage",
}


@dataclass
class WorktreeInfo:
    """Details of an isolation worktree created for a task execution."""

    path: Path
    branch: str
    snapshot_commit: str | None = None


class WorktreeManager:
    """Create and manage detached git worktrees for isolated task execution.

    All operations are best-effort: any failure (non-git directory, missing
    HEAD, git errors) is logged and reported as ``None``/``0`` so task
    execution can always fall back to running in the user's repo_root.
    """

    @staticmethod
    def is_enabled() -> bool:
        """Check whether worktree isolation is enabled.

        Returns:
            True unless NINJA_WORKTREE_MODE is set to "off".
        """
        return os.environ.get(WORKTREE_MODE_ENV, "on").strip().lower() != "off"

    def create(
        self,
        repo_root: str,
        task_hint: str = "",
        step_id: str = "",
    ) -> WorktreeInfo | None:
        """Create a feature branch and detached worktree for task isolation.

        Args:
            repo_root: Repository root path (main working tree).
            task_hint: Task description used for the branch slug/commit message.
            step_id: Step identifier used for the branch slug.

        Returns:
            WorktreeInfo on success, None on any fallback condition (not a git
            repo, no commits yet, worktree creation failure).
        """
        try:
            if not GitSafetyChecker.is_git_repo(repo_root):
                logger.debug("Worktree isolation skipped: not a git repository")
                return None

            # Auto-housekeeping: drop worktrees older than the threshold so the
            # cache cannot grow unbounded (tunable via NINJA_WORKTREE_MAX_AGE_DAYS).
            self.prune()

            if GitSafetyChecker.get_current_commit(repo_root) is None:
                logger.warning(
                    "Worktree isolation skipped: repository has no commits (missing HEAD); "
                    "falling back to running in repo_root"
                )
                return None

            root = Path(repo_root).resolve()
            branch = self._build_branch_name(task_hint=task_hint, step_id=step_id)
            worktree_path = self._worktree_path(root, branch)
            worktree_path.parent.mkdir(parents=True, exist_ok=True)

            result = subprocess.run(
                ["git", "worktree", "add", "-b", branch, str(worktree_path), "HEAD"],
                cwd=repo_root,
                capture_output=True,
                timeout=_GIT_TIMEOUT_SEC,
                check=False,
            )
            if result.returncode != 0:
                logger.warning(
                    f"Worktree creation failed ({result.stderr.decode(errors='replace').strip()}); "
                    "falling back to running in repo_root"
                )
                return None

            snapshot_commit = self._snapshot_dirty_state(
                repo_root=repo_root,
                worktree_path=worktree_path,
                task_hint=task_hint,
            )

            logger.info(f"🔀 Created isolation worktree: {worktree_path} (branch '{branch}')")
            return WorktreeInfo(
                path=worktree_path,
                branch=branch,
                snapshot_commit=snapshot_commit,
            )

        except Exception as e:
            logger.warning(f"Worktree isolation unavailable ({e}); falling back to repo_root")
            return None

    def prune(self, max_age_days: int | None = None) -> int:
        """Remove isolation worktrees older than max_age_days.

        Called automatically by :meth:`create` before making a new worktree so
        the cache does not grow unbounded. The threshold comes from
        ``NINJA_WORKTREE_MAX_AGE_DAYS`` when set, otherwise the default.

        Uses ``git worktree remove --force`` when the owning repository can be
        located (via the worktree's .git file), otherwise falls back to
        deleting the directory.

        Args:
            max_age_days: Age threshold in days (by directory mtime).

        Returns:
            Number of worktree directories removed.
        """
        if max_age_days is None:
            max_age_days = self._max_age_days()

        removed = 0
        base = get_cache_dir() / "worktrees"
        if not base.exists():
            return 0

        cutoff = time.time() - (max_age_days * _SECONDS_PER_DAY)
        for repo_dir in base.iterdir():
            if not repo_dir.is_dir():
                continue
            for worktree_dir in repo_dir.iterdir():
                if not worktree_dir.is_dir():
                    continue
                try:
                    if worktree_dir.stat().st_mtime > cutoff:
                        continue
                    if self._remove_worktree(worktree_dir):
                        removed += 1
                except OSError as e:
                    logger.warning(f"Failed to prune worktree {worktree_dir}: {e}")
            try:
                repo_dir.rmdir()  # Only succeeds when empty
            except OSError:
                pass

        return removed

    @staticmethod
    def _max_age_days() -> int:
        """Return the pruning age threshold (env-tunable).

        Returns:
            Days from NINJA_WORKTREE_MAX_AGE_DAYS, or the default.
        """
        try:
            return max(0, int(os.environ.get(WORKTREE_MAX_AGE_ENV, _DEFAULT_MAX_AGE_DAYS)))
        except (TypeError, ValueError):
            return _DEFAULT_MAX_AGE_DAYS

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _snapshot_dirty_state(
        self,
        repo_root: str,
        worktree_path: Path,
        task_hint: str,
    ) -> str | None:
        """Snapshot the main tree's uncommitted changes into the worktree.

        Tracked modifications are replayed via ``git diff HEAD --binary`` |
        ``git apply``; untracked files (respecting .gitignore via porcelain
        status) are copied with shutil. The snapshot is committed on the
        feature branch with the [ninja-auto-save] message format. The main
        working tree is only READ, never modified.

        Args:
            repo_root: Main repository root (read-only source).
            worktree_path: Path of the freshly created worktree.
            task_hint: Task description for the commit message.

        Returns:
            Snapshot commit hash, or None when there was nothing to snapshot
            or when the snapshot failed (logged; never raises).
        """
        try:
            has_changes, changed_files = GitSafetyChecker.has_uncommitted_changes(repo_root)
            if not has_changes:
                return None

            base_head = self._rev_parse(worktree_path)

            # 1. Replay tracked modifications (staged + unstaged) into the worktree.
            diff_result = subprocess.run(
                ["git", "diff", "HEAD", "--binary"],
                cwd=repo_root,
                capture_output=True,
                timeout=_GIT_TIMEOUT_SEC,
                check=False,
            )
            if diff_result.returncode == 0 and diff_result.stdout:
                apply_result = subprocess.run(
                    ["git", "apply", "--whitespace=nowarn"],
                    cwd=worktree_path,
                    input=diff_result.stdout,
                    capture_output=True,
                    timeout=_GIT_TIMEOUT_SEC,
                    check=False,
                )
                if apply_result.returncode != 0:
                    logger.warning(
                        "Worktree snapshot: failed to apply tracked diff "
                        f"({apply_result.stderr.decode(errors='replace').strip()}); "
                        "continuing with untracked files only"
                    )

            # 2. Copy untracked files (porcelain status respects .gitignore).
            status_result = subprocess.run(
                ["git", "status", "--porcelain", "--untracked-files=all"],
                cwd=repo_root,
                capture_output=True,
                text=True,
                timeout=_GIT_TIMEOUT_SEC,
                check=False,
            )
            if status_result.returncode == 0:
                for line in status_result.stdout.splitlines():
                    if not line.startswith("?? "):
                        continue
                    rel_path = line[3:].strip().strip('"')
                    if not rel_path:
                        continue
                    # Never copy heavy/transient directories into the snapshot
                    # (node_modules alone can be >1GB and bloat the cache).
                    if any(part in SNAPSHOT_EXCLUDED_DIRS for part in rel_path.split("/")):
                        continue
                    source = Path(repo_root) / rel_path
                    if not source.is_file():
                        continue
                    destination = worktree_path / rel_path
                    try:
                        destination.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(source, destination)
                    except OSError as e:
                        logger.warning(f"Worktree snapshot: failed to copy {rel_path}: {e}")

            # 3. Commit the snapshot on the feature branch (auto_commit_changes
            #    runs with cwd=worktree_path, so the main repo is untouched).
            committed = GitSafetyChecker.auto_commit_changes(
                str(worktree_path), task_hint, changed_files
            )
            if not committed:
                logger.warning("Worktree snapshot commit failed; task continues without it")
                return None

            new_head = self._rev_parse(worktree_path)
            if new_head and new_head != base_head:
                return new_head
            return None

        except Exception as e:
            logger.warning(f"Worktree snapshot failed ({e}); task continues without it")
            return None

    def _build_branch_name(self, task_hint: str, step_id: str) -> str:
        """Build a unique feature branch name: ninja/<slug>-<timestamp>-<uid>.

        Args:
            task_hint: Task description (fallback slug source).
            step_id: Step identifier (preferred slug source).

        Returns:
            Branch name of at most 40 characters.
        """
        source = (step_id or task_hint or "task").lower()
        slug = re.sub(r"[^a-z0-9]+", "-", source).strip("-")
        slug = slug[:_MAX_SLUG_LEN].rstrip("-") or "task"
        timestamp = int(time.time())
        unique = uuid.uuid4().hex[:_UNIQUE_SUFFIX_LEN]
        return f"{_BRANCH_PREFIX}{slug}-{timestamp}-{unique}"

    def _worktree_path(self, repo_root: Path, branch: str) -> Path:
        """Compute the worktree directory under the ninja-mcp cache dir.

        Args:
            repo_root: Resolved repository root path.
            branch: Feature branch name (slashes are flattened).

        Returns:
            Absolute path for the new worktree.
        """
        repo_hash = hashlib.sha256(str(repo_root).encode()).hexdigest()[:_REPO_HASH_LEN]
        branch_dir = branch.replace("/", "__")
        return get_cache_dir() / "worktrees" / repo_hash / branch_dir

    def _rev_parse(self, path: Path) -> str | None:
        """Resolve HEAD in the given work tree.

        Args:
            path: Working tree path.

        Returns:
            Commit hash or None on failure.
        """
        try:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=path,
                capture_output=True,
                text=True,
                timeout=_GIT_TIMEOUT_SEC,
                check=False,
            )
            return result.stdout.strip() if result.returncode == 0 else None
        except Exception:
            return None

    def _remove_worktree(self, worktree_dir: Path) -> bool:
        """Remove a single worktree directory, preferring git bookkeeping.

        Args:
            worktree_dir: Worktree directory to remove.

        Returns:
            True if the directory no longer exists afterwards.
        """
        repo_dir = self._locate_main_repo(worktree_dir)
        if repo_dir is not None:
            result = subprocess.run(
                ["git", "-C", str(repo_dir), "worktree", "remove", "--force", str(worktree_dir)],
                capture_output=True,
                timeout=_GIT_TIMEOUT_SEC,
                check=False,
            )
            if result.returncode == 0:
                return True

        # Fallback: plain directory removal (leaves stale admin entries for
        # `git worktree prune`, which is acceptable for a manual helper).
        shutil.rmtree(worktree_dir, ignore_errors=True)
        return not worktree_dir.exists()

    def _locate_main_repo(self, worktree_dir: Path) -> Path | None:
        """Locate the main repository for a worktree via its .git file.

        Args:
            worktree_dir: Worktree directory containing a .git file.

        Returns:
            Path of the main working tree top level, or None if unknown.
        """
        try:
            git_file = worktree_dir / ".git"
            if not git_file.is_file():
                return None
            content = git_file.read_text().strip()
            if not content.startswith("gitdir: "):
                return None
            # gitdir points at <repo>/.git/worktrees/<id>; the main git dir
            # is two levels up, and the work tree top level is its parent.
            main_git_dir = Path(content.removeprefix("gitdir: ")).parent.parent
            if main_git_dir.name == ".git":
                return main_git_dir.parent
            return main_git_dir
        except OSError:
            return None
