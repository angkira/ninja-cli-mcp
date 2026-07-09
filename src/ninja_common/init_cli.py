"""ninja-mcp init CLI — installs ninja MCP servers into host config files."""

from __future__ import annotations

import argparse
import sys
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from collections.abc import Callable

    from ninja_common.init_targets._json_target import JsonMcpTarget


# ── JSON-target registry ───────────────────────────────────────────────────────
# Each entry: (command_name, target_instance, help_text)
# Adding a new JSON-based MCP host is as simple as adding an entry here
# (after creating a thin module in init_targets/).

_JSON_TARGETS: list[tuple[str, JsonMcpTarget, str]] = []


def _register_json_target(command: str, target: JsonMcpTarget, help_text: str = "") -> None:
    _JSON_TARGETS.append((command, target, help_text or target.help_text))


# ── build parser ───────────────────────────────────────────────────────────────


def _build_parser() -> argparse.ArgumentParser:
    """Build and return the top-level argument parser."""
    parser = argparse.ArgumentParser(
        prog="ninja-mcp",
        description="ninja-mcp: install and manage MCP server configuration.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Show plugin-mode install instructions for Claude Code
  ninja-mcp init claude-code

  # Directly merge servers into ~/.claude/settings.json
  ninja-mcp init claude-code --direct

  # Preview what would be written (no disk writes)
  ninja-mcp init codex --dry-run

  # Merge into ~/.codex/config.toml (overwrite conflicts)
  ninja-mcp init codex --force

  # Merge into ~/.cursor/mcp.json
  ninja-mcp init cursor

  # Install into Google Antigravity
  ninja-mcp init antigravity

  # Print mcp.json for any generic MCP host
  ninja-mcp init generic

  # Detect which hosts are installed on this machine
  ninja-mcp init detect
        """,
    )

    sub = parser.add_subparsers(dest="top_command", metavar="COMMAND")

    # ── init ──────────────────────────────────────────────────────────────────
    init_parser = sub.add_parser("init", help="Install MCP servers into a host config file.")
    init_sub = init_parser.add_subparsers(dest="host", metavar="HOST")
    init_parser.set_defaults(func=_cmd_init_help, init_parser=init_parser)

    # claude-code
    cc_parser = init_sub.add_parser(
        "claude-code",
        help="Install into Claude Code (plugin mode or --direct).",
    )
    cc_parser.add_argument(
        "--direct",
        action="store_true",
        help="Write directly into ~/.claude/settings.json instead of printing plugin instructions.",
    )
    cc_parser.add_argument(
        "--dry-run",
        action="store_true",
        dest="dry_run",
        help="Print the diff without writing to disk.",
    )
    cc_parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite servers that already exist in the target file.",
    )
    cc_parser.set_defaults(func=_cmd_claude_code)

    # codex
    codex_parser = init_sub.add_parser(
        "codex",
        help="Merge into ~/.codex/config.toml.",
    )
    codex_parser.add_argument(
        "--dry-run",
        action="store_true",
        dest="dry_run",
        help="Print the diff without writing to disk.",
    )
    codex_parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite sections that already exist in the target file.",
    )
    codex_parser.set_defaults(func=_cmd_codex)

    # ── auto-registered JSON targets ─────────────────────────────────────────
    for cmd_name, tgt, _ in _JSON_TARGETS:
        p = init_sub.add_parser(cmd_name, help=tgt.help_text)
        tgt.add_arguments(p)
        p.set_defaults(func=_cmd_json_target, _json_target=tgt)

    # generic
    generic_parser = init_sub.add_parser(
        "generic",
        help="Print mcp.json to stdout for Windsurf / Claude Desktop / VS Code Copilot.",
    )
    generic_parser.set_defaults(func=_cmd_generic)

    # detect
    detect_parser = init_sub.add_parser(
        "detect",
        help="Detect which MCP hosts are installed on this machine.",
    )
    detect_parser.set_defaults(func=_cmd_detect)

    return parser


# ── command handlers ───────────────────────────────────────────────────────────


def _cmd_init_help(args: argparse.Namespace) -> int:
    """Print init subcommand help when no host is specified."""
    init_parser: argparse.ArgumentParser = args.init_parser
    init_parser.print_help()
    return 0


def _cmd_claude_code(args: argparse.Namespace) -> int:
    """Dispatch to the claude_code install target."""
    from ninja_common.init_targets import claude_code

    return claude_code.install(args)


def _cmd_codex(args: argparse.Namespace) -> int:
    """Dispatch to the codex install target."""
    from ninja_common.init_targets import codex

    return codex.install(args)


def _cmd_json_target(args: argparse.Namespace) -> int:
    """Generic dispatch for all JSON-based install targets."""
    target: JsonMcpTarget = args._json_target
    return target.install(args)


def _cmd_generic(args: argparse.Namespace) -> int:
    """Dispatch to the generic install target."""
    from ninja_common.init_targets import generic

    return generic.install(args)


def _cmd_detect(args: argparse.Namespace) -> int:
    """Print which MCP hosts are detected on this machine."""
    _ = args
    from ninja_common.init_targets import claude_code, codex, generic

    targets: list[tuple[str, Callable[[], bool], str]] = [
        ("claude-code", claude_code.detect, "~/.claude/"),
        ("codex", codex.detect, "~/.codex/"),
        *[t.as_detect_tuple() for _, t, _ in _JSON_TARGETS],
        ("generic", generic.detect, "(always available)"),
    ]

    found_any = False
    for name, detect_fn, location in targets:
        if detect_fn():
            print(f"  {name:15s}  detected   [{location}]")
            found_any = True
        else:
            print(f"  {name:15s}  not found  [{location}]")

    if not found_any:
        print()
        print("No known MCP hosts detected on this machine.")
        print("Use 'ninja-mcp init generic' to print the mcp.json snippet.")
    return 0


# ── entry point ────────────────────────────────────────────────────────────────


def main() -> None:
    """Entry point for the ninja-mcp console script."""
    _populate_json_targets()
    parser = _build_parser()
    args = parser.parse_args()

    if not hasattr(args, "func"):
        parser.print_help()
        sys.exit(0)

    func: Callable[[argparse.Namespace], int] = args.func
    sys.exit(func(args))


# ── registry population (imports are deferred to avoid circular deps) ──────────


def _populate_json_targets() -> None:
    """Lazily populate the JSON target registry.

    This must be called **before** _build_parser() so that all targets appear
    in the CLI.  Imports are deferred here to keep ``ninja-mcp --help`` fast.
    """
    if _JSON_TARGETS:
        return  # already populated

    from ninja_common.init_targets import (
        antigravity,
        cursor,
        kiro,
        roo_code,
        vscode_cline,
        windsurf,
    )

    _register_json_target(
        "antigravity",
        antigravity.antigravity,
        "Install into Google Antigravity IDE (~/.gemini/config/mcp_config.json).",
    )
    _register_json_target(
        "cursor",
        cursor._cursor_target,
        "Merge into ~/.cursor/mcp.json.",
    )
    _register_json_target(
        "kiro",
        kiro.kiro,
        "Merge into ~/.kiro/settings/mcp.json.",
    )
    _register_json_target(
        "roo-code",
        roo_code.roo_code,
        "Merge into ~/.config/roo/mcp_settings.json.",
    )
    _register_json_target(
        "vscode-cline",
        vscode_cline.vscode_cline,
        "Merge into ~/.config/Code/User/mcp.json.",
    )
    _register_json_target(
        "windsurf",
        windsurf.windsurf,
        "Merge into ~/.windsurf/mcp.json.",
    )


# Populate the JSON target registry at import time so that
# ``_build_parser()`` and ``_cmd_detect()`` always see the full list
# (even when called by tests or from the unified CLI wrapper).
_populate_json_targets()


if __name__ == "__main__":
    main()
