"""
Path utilities with security protections.

This module provides utilities for safe path handling, ensuring that
all paths remain within allowed boundaries (repo_root).
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path


class PathTraversalError(Exception):
    """Raised when a path traversal attempt is detected."""

    pass


def get_cache_dir() -> Path:
    """
    Get the global ninja-mcp cache directory.

    Returns XDG Base Directory compliant cache location:
    - Linux/macOS: ~/.cache/ninja-mcp
    - Windows: %LOCALAPPDATA%/ninja-mcp

    Returns:
        Path to the ninja-mcp cache directory.
    """
    if os.name == "nt":  # Windows
        cache_base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:  # Linux/macOS
        cache_base = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))

    cache_dir = cache_base / "ninja-mcp"
    cache_dir.mkdir(parents=True, exist_ok=True)

    return cache_dir


def safe_resolve(path: str | Path, root: str | Path) -> Path:
    """
    Resolve a path safely within a root directory.

    Args:
        path: The path to resolve (can be relative or absolute).
        root: The root directory that the path must stay within.

    Returns:
        The resolved absolute path.

    Raises:
        PathTraversalError: If the resolved path is outside the root.
    """
    root_path = Path(root).resolve()

    resolved = Path(path).resolve() if Path(path).is_absolute() else (root_path / path).resolve()

    # Additional canonicalization to prevent symbolic link traversal
    try:
        resolved.relative_to(root_path)
    except ValueError as err:
        raise PathTraversalError(
            f"Path '{path}' resolves to '{resolved}' which is outside root '{root_path}'"
        ) from err

    return resolved


def validate_repo_root(repo_root: str) -> Path:
    """
    Validate that repo_root exists and is a directory.

    Args:
        repo_root: The repository root path to validate.

    Returns:
        The resolved Path object.

    Raises:
        ValueError: If the path doesn't exist or isn't a directory.
    """
    path = Path(repo_root).resolve()

    if not path.exists():
        raise ValueError(f"Repository root does not exist: {repo_root}")

    if not path.is_dir():
        raise ValueError(f"Repository root is not a directory: {repo_root}")

    # Additional security check: ensure it's not a sensitive system directory
    sensitive_dirs = ["/etc", "/bin", "/sbin", "/usr/bin", "/usr/sbin", "/root", "/boot"]
    path_str = str(path)
    for sensitive in sensitive_dirs:
        if path_str.startswith(sensitive):
            raise ValueError(f"Repository root cannot be in sensitive directory: {sensitive}")

    return path


def get_internal_dir(repo_root: str | Path) -> Path:
    """
    Get the internal directory for ninja-mcp data.

    Uses a centralized cache directory instead of polluting project directories.
    Logs and metadata are stored in ~/.cache/ninja-mcp/<repo_hash>/

    Args:
        repo_root: The repository root path.

    Returns:
        Path to the ninja-mcp cache directory for this repo.
    """
    # Get cache directory (XDG Base Directory compliant)
    if os.name == "nt":  # Windows
        cache_base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:  # Linux/macOS
        cache_base = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))

    # Create a stable hash of the repo path
    root = Path(repo_root).resolve()
    repo_hash = hashlib.sha256(str(root).encode()).hexdigest()[:16]

    # Use format: ~/.cache/ninja-mcp/<hash>-<repo_name>/
    repo_name = root.name
    internal = cache_base / "ninja-mcp" / f"{repo_hash}-{repo_name}"

    return internal


def ensure_internal_dirs(repo_root: str | Path) -> dict[str, Path]:
    """
    Ensure internal directories exist and return their paths.

    Creates directories in the centralized cache location (~/.cache/ninja-mcp/)
    instead of polluting the project directory.

    Args:
        repo_root: The repository root path (used to generate unique cache dir).

    Returns:
        Dict with paths to logs, tasks, and metadata directories in cache.
    """
    internal = get_internal_dir(repo_root)

    dirs = {
        "root": internal,
        "logs": internal / "logs",
        "tasks": internal / "tasks",
        "metadata": internal / "metadata",
        "work": internal / "work",  # Isolated work directories for concurrent tasks
    }

    for dir_path in dirs.values():
        dir_path.mkdir(parents=True, exist_ok=True)
        # Set secure permissions (read/write/execute for owner only)
        dir_path.chmod(0o700)

    return dirs


def safe_join(base: str | Path, *parts: str) -> Path:
    """
    Safely join path components, preventing traversal.

    Args:
        base: Base directory path.
        *parts: Path components to join.

    Returns:
        Joined path that is guaranteed to be within base.

    Raises:
        PathTraversalError: If resulting path would be outside base.
    """
    base_path = Path(base).resolve()

    # Clean each part to remove any traversal attempts
    clean_parts = []
    for part in parts:
        # Remove leading slashes and resolve any . or ..
        cleaned = part.lstrip("/\\")
        # Split and filter out dangerous components
        segments = cleaned.replace("\\", "/").split("/")
        safe_segments = [s for s in segments if s and s not in {"..", "."}]
        clean_parts.extend(safe_segments)

    result = base_path
    for part in clean_parts:
        result = result / part

    # Final verification with additional canonicalization
    try:
        result.resolve().relative_to(base_path)
    except ValueError as err:
        raise PathTraversalError(
            f"Path components {parts} would escape base directory {base_path}"
        ) from err

    return result


def is_path_within(path: str | Path, root: str | Path) -> bool:
    """
    Check if a path is within a root directory with enhanced security.

    Args:
        path: Path to check.
        root: Root directory.

    Returns:
        True if path is within root, False otherwise.
    """
    try:
        path_obj = Path(path).resolve()
        root_obj = Path(root).resolve()

        # Additional check for symbolic links
        if path_obj.is_symlink():
            # Resolve the symlink target and check if it's within root
            target = path_obj.readlink().resolve()
            target.relative_to(root_obj)

        path_obj.relative_to(root_obj)
        return True
    except (ValueError, OSError):
        return False


def normalize_globs(globs: list[str], repo_root: str | Path) -> list[str]:
    """
    Normalize glob patterns relative to repo root.

    Args:
        globs: List of glob patterns.
        repo_root: Repository root path.

    Returns:
        Normalized glob patterns.
    """
    root = Path(repo_root).resolve()
    normalized = []

    for glob in globs:
        # If it's an absolute path, make it relative
        if Path(glob).is_absolute():
            try:
                rel = Path(glob).relative_to(root)
                normalized.append(str(rel))
            except ValueError:
                # Path outside repo root, skip it
                continue
        else:
            normalized.append(glob)

    return normalized
