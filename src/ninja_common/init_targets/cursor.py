"""Install target: Cursor IDE (~/.cursor/mcp.json)."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from ninja_common.init_targets._json_target import JsonMcpTarget
from ninja_common.init_targets._json_target import target as _make_target


if TYPE_CHECKING:
    import argparse

# ── overridable paths (monkey-patched by tests) ────────────────────────────────

_CURSOR_DIR: Path = Path.home() / ".cursor"
_MCP_FILE: Path = _CURSOR_DIR / "mcp.json"

# Internal target that reads the overridable globals above.
_cursor_target = _make_target(
    name="cursor",
    display_name="Cursor IDE",
    config_dir=_CURSOR_DIR,
    config_file=_MCP_FILE,
    detect_dir=_CURSOR_DIR,
)


def detect() -> bool:
    """Return True when ~/.cursor/ exists (Cursor IDE is installed)."""
    return _CURSOR_DIR.is_dir()


def install(args: argparse.Namespace) -> int:
    """Merge ninja servers into ~/.cursor/mcp.json."""
    target = JsonMcpTarget(
        name="cursor",
        display_name="Cursor IDE",
        config_dir=_CURSOR_DIR,
        config_file=_MCP_FILE,
        detect_dir=_CURSOR_DIR,
    )
    return target.install(args)
