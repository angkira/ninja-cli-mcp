"""Tests for path utilities."""

from __future__ import annotations

from pathlib import Path

import pytest

from ninja_cli_mcp.path_utils import (
    PathTraversalError,
    ensure_internal_dirs,
    get_internal_dir,
    is_path_within,
    normalize_globs,
    safe_join,
    safe_resolve,
    validate_repo_root,
)


class TestSafeResolve:
    """Tests for safe_resolve function."""

    def test_relative_path_within_root(self, temp_dir: Path) -> None:
        result = safe_resolve("subdir/file.txt", temp_dir)
        expected = (temp_dir / "subdir" / "file.txt").resolve()
        assert result == expected

    def test_absolute_path_within_root(self, temp_dir: Path) -> None:
        abs_path = temp_dir / "subdir" / "file.txt"
        result = safe_resolve(str(abs_path), temp_dir)
        assert result == abs_path.resolve()

    def test_path_traversal_blocked(self, temp_dir: Path) -> None:
        with pytest.raises(PathTraversalError):
            safe_resolve("../outside", temp_dir)

    def test_absolute_path_outside_root_blocked(self, temp_dir: Path) -> None:
        with pytest.raises(PathTraversalError):
            safe_resolve("/etc/passwd", temp_dir)

    def test_dot_dot_in_middle_blocked(self, temp_dir: Path) -> None:
        with pytest.raises(PathTraversalError):
            safe_resolve("subdir/../../outside", temp_dir)


class TestValidateRepoRoot:
    """Tests for validate_repo_root function."""

    def test_valid_directory(self, temp_dir: Path) -> None:
        result = validate_repo_root(str(temp_dir))
        assert result == temp_dir.resolve()

    def test_nonexistent_path(self) -> None:
        with pytest.raises(ValueError, match="does not exist"):
            validate_repo_root("/nonexistent/path/12345")

    def test_file_not_directory(self, temp_dir: Path) -> None:
        file_path = temp_dir / "file.txt"
        file_path.write_text("content")

        with pytest.raises(ValueError, match="not a directory"):
            validate_repo_root(str(file_path))


class TestGetInternalDir:
    """Tests for get_internal_dir function."""

    def test_returns_correct_path(self, temp_dir: Path) -> None:
        result = get_internal_dir(temp_dir)
        assert result == (temp_dir / ".ninja-cli-mcp").resolve()

    def test_accepts_string_path(self, temp_dir: Path) -> None:
        result = get_internal_dir(str(temp_dir))
        assert result == (temp_dir / ".ninja-cli-mcp").resolve()


class TestEnsureInternalDirs:
    """Tests for ensure_internal_dirs function."""

    def test_creates_directories(self, temp_dir: Path) -> None:
        dirs = ensure_internal_dirs(temp_dir)

        assert dirs["root"].exists()
        assert dirs["logs"].exists()
        assert dirs["tasks"].exists()
        assert dirs["metadata"].exists()

    def test_idempotent(self, temp_dir: Path) -> None:
        dirs1 = ensure_internal_dirs(temp_dir)
        dirs2 = ensure_internal_dirs(temp_dir)

        assert dirs1 == dirs2

    def test_correct_structure(self, temp_dir: Path) -> None:
        dirs = ensure_internal_dirs(temp_dir)

        assert dirs["logs"] == (temp_dir / ".ninja-cli-mcp" / "logs").resolve()
        assert dirs["tasks"] == (temp_dir / ".ninja-cli-mcp" / "tasks").resolve()
        assert dirs["metadata"] == (temp_dir / ".ninja-cli-mcp" / "metadata").resolve()


class TestSafeJoin:
    """Tests for safe_join function."""

    def test_simple_join(self, temp_dir: Path) -> None:
        result = safe_join(temp_dir, "subdir", "file.txt")
        assert result == (temp_dir / "subdir" / "file.txt").resolve()

    def test_strips_leading_slashes(self, temp_dir: Path) -> None:
        result = safe_join(temp_dir, "/subdir", "file.txt")
        assert result == (temp_dir / "subdir" / "file.txt").resolve()

    def test_filters_dot_dot(self, temp_dir: Path) -> None:
        result = safe_join(temp_dir, "subdir", "..", "file.txt")
        # .. should be filtered out
        assert result == (temp_dir / "subdir" / "file.txt").resolve()

    def test_filters_single_dot(self, temp_dir: Path) -> None:
        result = safe_join(temp_dir, ".", "subdir", ".", "file.txt")
        assert result == (temp_dir / "subdir" / "file.txt").resolve()

    def test_handles_backslashes(self, temp_dir: Path) -> None:
        result = safe_join(temp_dir, "subdir\\nested", "file.txt")
        assert result == (temp_dir / "subdir" / "nested" / "file.txt").resolve()


class TestIsPathWithin:
    """Tests for is_path_within function."""

    def test_path_within_root(self, temp_dir: Path) -> None:
        assert is_path_within(temp_dir / "subdir", temp_dir) is True

    def test_path_is_root(self, temp_dir: Path) -> None:
        assert is_path_within(temp_dir, temp_dir) is True

    def test_path_outside_root(self, temp_dir: Path) -> None:
        assert is_path_within("/etc/passwd", temp_dir) is False

    def test_sibling_path(self, temp_dir: Path) -> None:
        sibling = temp_dir.parent / "sibling"
        assert is_path_within(sibling, temp_dir) is False


class TestNormalizeGlobs:
    """Tests for normalize_globs function."""

    def test_relative_globs_unchanged(self, temp_dir: Path) -> None:
        globs = ["**/*.py", "src/**", "*.md"]
        result = normalize_globs(globs, temp_dir)
        assert result == globs

    def test_absolute_paths_made_relative(self, temp_dir: Path) -> None:
        # Resolve temp_dir to handle macOS symlinks (/var -> /private/var)
        temp_dir_resolved = temp_dir.resolve()
        abs_path = str(temp_dir_resolved / "src")
        globs = [abs_path, "**/*.py"]
        result = normalize_globs(globs, temp_dir_resolved)
        assert "src" in result
        assert "**/*.py" in result

    def test_paths_outside_root_filtered(self, temp_dir: Path) -> None:
        globs = ["/etc/passwd", "**/*.py"]
        result = normalize_globs(globs, temp_dir)
        assert "/etc/passwd" not in result
        assert "**/*.py" in result
