"""Shared helpers for ninja-mcp init targets."""

from __future__ import annotations

import importlib.resources
import json
from pathlib import Path
from typing import Any


def _dist_path(filename: str) -> Path:
    """Return an absolute path to a file shipped in the ninja_common/dist/ package data."""
    try:
        ref = importlib.resources.files("ninja_common") / "dist" / filename
        with importlib.resources.as_file(ref) as p:
            return Path(str(p))
    except (FileNotFoundError, TypeError):
        # Fallback: locate relative to this file (editable installs)
        here = Path(__file__).parent.parent
        candidate = here / "dist" / filename
        if candidate.exists():
            return candidate
        raise FileNotFoundError(f"Package data file not found: {filename}") from None


def load_mcp_json() -> dict[str, Any]:
    """Load dist/mcp.json and return its parsed contents."""
    path = _dist_path("mcp.json")
    with path.open() as fh:
        return json.load(fh)


def load_codex_toml_text() -> str:
    """Return the raw text of dist/codex.toml."""
    path = _dist_path("codex.toml")
    return path.read_text()


def atomic_write(path: Path, content: str) -> None:
    """Write *content* to *path* atomically via a sibling .tmp file."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(path)


def ensure_backup(path: Path) -> None:
    """Create a one-time backup at ``<path>.pre-ninja.bak`` if it does not yet exist."""
    bak = Path(str(path) + ".pre-ninja.bak")
    if path.exists() and not bak.exists():
        import shutil

        shutil.copy2(path, bak)


def restore_backup(path: Path) -> None:
    """Restore the ``.pre-ninja.bak`` backup and remove the corrupt file."""
    bak = Path(str(path) + ".pre-ninja.bak")
    if bak.exists():
        import shutil

        shutil.copy2(bak, path)


def diff_lines(before: str, after: str, label: str = "") -> str:
    """Return a simple unified-diff string between *before* and *after*."""
    import difflib

    before_lines = before.splitlines(keepends=True)
    after_lines = after.splitlines(keepends=True)
    diff = difflib.unified_diff(
        before_lines,
        after_lines,
        fromfile=f"{label} (current)" if label else "current",
        tofile=f"{label} (new)" if label else "new",
    )
    return "".join(diff)
