"""Install target: Claude Code (~/.claude/)."""

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

_CLAUDE_DIR = Path.home() / ".claude"
_SETTINGS_FILE = _CLAUDE_DIR / "settings.json"

# Repository URL — read from marketplace.json when available.
_FALLBACK_REPO_URL = "https://github.com/ninja-mcp/ninja-cli-mcp"


def detect() -> bool:
    """Return True when ~/.claude/ exists (Claude Code is installed)."""
    return _CLAUDE_DIR.is_dir()


def _get_repo_url() -> str:
    """Read repository URL from .claude-plugin/marketplace.json or pyproject.toml."""
    import importlib.resources

    try:
        ref = importlib.resources.files("ninja_common").parent.parent
        marketplace = Path(str(ref)) / ".claude-plugin" / "marketplace.json"
        if marketplace.exists():
            data = json.loads(marketplace.read_text())
            plugins = data.get("plugins", [])
            if plugins:
                return plugins[0].get("repository", _FALLBACK_REPO_URL)
    except Exception:  # broad: filesystem + JSON + importlib errors all degrade gracefully
        pass
    return _FALLBACK_REPO_URL


def _plugin_mode_instructions() -> None:
    """Print plugin-mode install instructions to stdout."""
    repo_url = _get_repo_url()
    print("Claude Code — plugin install (recommended)")
    print()
    print("Run the following inside Claude Code:")
    print()
    print(f"  /plugin install ninja@{repo_url}")
    print()
    print(
        "This installs all 4 MCP servers (ninja-coder, ninja-researcher,\n"
        "ninja-secretary, ninja-prompts) plus Claude Code skills and agents."
    )
    print()
    print("To install directly into ~/.claude/settings.json instead, use:")
    print("  ninja-mcp init claude-code --direct")


def _merge_settings(
    existing: dict[str, Any],
    incoming: dict[str, Any],
    force: bool,
    dry_run: bool,
) -> tuple[dict[str, Any], list[str]]:
    """Merge *incoming* mcpServers into *existing* settings.

    Returns ``(merged_dict, conflicts)`` where *conflicts* is a list of server
    names that already existed and were NOT overwritten (because *force* is False).
    """
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
    """Install ninja MCP servers into Claude Code.

    Returns 0 on success, non-zero on failure.
    """
    direct: bool = getattr(args, "direct", False)
    dry_run: bool = getattr(args, "dry_run", False)
    force: bool = getattr(args, "force", False)

    if not direct:
        _plugin_mode_instructions()
        return 0

    # --direct mode: merge into ~/.claude/settings.json
    incoming = load_mcp_json()

    existing: dict[str, Any] = {}
    if _SETTINGS_FILE.exists():
        try:
            existing = json.loads(_SETTINGS_FILE.read_text())
        except json.JSONDecodeError as exc:
            print(f"Error: ~/.claude/settings.json is not valid JSON: {exc}", file=sys.stderr)
            return 1

    merged, conflicts = _merge_settings(existing, incoming, force=force, dry_run=dry_run)

    if conflicts and not force:
        print(
            f"Error: the following servers already exist in {_SETTINGS_FILE}:\n"
            f"  {', '.join(conflicts)}\n"
            "Pass --force to overwrite them.",
            file=sys.stderr,
        )
        return 1

    before_text = json.dumps(existing, indent=2) if existing else ""
    after_text = json.dumps(merged, indent=2)

    if dry_run:
        print(f"Dry run — would write to {_SETTINGS_FILE}")
        print()
        if before_text:
            print(diff_lines(before_text + "\n", after_text + "\n", str(_SETTINGS_FILE)))
        else:
            print(after_text)
        return 0

    _CLAUDE_DIR.mkdir(parents=True, exist_ok=True)
    ensure_backup(_SETTINGS_FILE)

    try:
        atomic_write(_SETTINGS_FILE, after_text + "\n")
    except Exception as exc:
        print(f"Error writing {_SETTINGS_FILE}: {exc}", file=sys.stderr)
        restore_backup(_SETTINGS_FILE)
        return 1

    print(f"Written: {_SETTINGS_FILE}")
    added = [n for n in incoming.get("mcpServers", {}) if n not in conflicts]
    for name in added:
        print(f"  + {name}")
    for name in conflicts:
        print(f"  ~ {name} (skipped — already exists)")
    return 0
