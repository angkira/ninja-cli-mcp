"""Install target: Cursor (~/.cursor/mcp.json)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ninja_common.init_targets._common import (
    atomic_write,
    diff_lines,
    ensure_backup,
    load_mcp_json,
    restore_backup,
)


if TYPE_CHECKING:
    import argparse

_CURSOR_DIR = Path.home() / ".cursor"
_MCP_FILE = _CURSOR_DIR / "mcp.json"


def detect() -> bool:
    """Return True when ~/.cursor/ exists (Cursor IDE is installed)."""
    return _CURSOR_DIR.is_dir()


def _merge_servers(
    existing: dict[str, Any],
    incoming: dict[str, Any],
    force: bool,
) -> tuple[dict[str, Any], list[str]]:
    """Merge mcpServers from *incoming* into *existing*."""
    merged = dict(existing)
    mcp_servers: dict[str, Any] = dict(existing.get("mcpServers", {}))
    incoming_servers: dict[str, Any] = incoming.get("mcpServers", {})

    conflicts: list[str] = []
    for name, config in incoming_servers.items():
        if name in mcp_servers and not force:
            conflicts.append(name)
        else:
            mcp_servers[name] = config

    merged["mcpServers"] = mcp_servers
    return merged, conflicts


def install(args: argparse.Namespace) -> int:
    """Merge ninja servers into ~/.cursor/mcp.json.

    Returns 0 on success, non-zero on failure.
    """
    dry_run: bool = getattr(args, "dry_run", False)
    force: bool = getattr(args, "force", False)

    incoming = load_mcp_json()

    existing: dict[str, Any] = {}
    if _MCP_FILE.exists():
        try:
            existing = json.loads(_MCP_FILE.read_text())
        except json.JSONDecodeError as exc:
            print(f"Error: {_MCP_FILE} is not valid JSON: {exc}", file=sys.stderr)
            return 1

    merged, conflicts = _merge_servers(existing, incoming, force=force)

    if conflicts and not force:
        print(
            f"Error: the following servers already exist in {_MCP_FILE}:\n"
            f"  {', '.join(conflicts)}\n"
            "Pass --force to overwrite them.",
            file=sys.stderr,
        )
        return 1

    before_text = json.dumps(existing, indent=2) if existing else ""
    after_text = json.dumps(merged, indent=2)

    if dry_run:
        print(f"Dry run — would write to {_MCP_FILE}")
        print()
        if before_text:
            print(diff_lines(before_text + "\n", after_text + "\n", str(_MCP_FILE)))
        else:
            print(after_text)
        return 0

    _CURSOR_DIR.mkdir(parents=True, exist_ok=True)
    ensure_backup(_MCP_FILE)

    try:
        atomic_write(_MCP_FILE, after_text + "\n")
    except Exception as exc:
        print(f"Error writing {_MCP_FILE}: {exc}", file=sys.stderr)
        restore_backup(_MCP_FILE)
        return 1

    print(f"Written: {_MCP_FILE}")
    added = [n for n in incoming.get("mcpServers", {}) if n not in conflicts]
    for name in added:
        print(f"  + {name}")
    for name in conflicts:
        print(f"  ~ {name} (skipped — already exists)")
    return 0
