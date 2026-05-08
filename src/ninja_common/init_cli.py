"""ninja-mcp init CLI — installs ninja MCP servers into host config files."""

from __future__ import annotations

import argparse
import sys
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from collections.abc import Callable


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

    # cursor
    cursor_parser = init_sub.add_parser(
        "cursor",
        help="Merge into ~/.cursor/mcp.json.",
    )
    cursor_parser.add_argument(
        "--dry-run",
        action="store_true",
        dest="dry_run",
        help="Print the diff without writing to disk.",
    )
    cursor_parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite servers that already exist in the target file.",
    )
    cursor_parser.set_defaults(func=_cmd_cursor)

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


def _cmd_cursor(args: argparse.Namespace) -> int:
    """Dispatch to the cursor install target."""
    from ninja_common.init_targets import cursor

    return cursor.install(args)


def _cmd_generic(args: argparse.Namespace) -> int:
    """Dispatch to the generic install target."""
    from ninja_common.init_targets import generic

    return generic.install(args)


def _cmd_detect(args: argparse.Namespace) -> int:
    """Print which MCP hosts are detected on this machine."""
    _ = args
    from ninja_common.init_targets import claude_code, codex, cursor, generic

    targets: list[tuple[str, Callable[[], bool], str]] = [
        ("claude-code", claude_code.detect, "~/.claude/"),
        ("codex", codex.detect, "~/.codex/"),
        ("cursor", cursor.detect, "~/.cursor/"),
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
    parser = _build_parser()
    args = parser.parse_args()

    if not hasattr(args, "func"):
        parser.print_help()
        sys.exit(0)

    func: Callable[[argparse.Namespace], int] = args.func
    sys.exit(func(args))


if __name__ == "__main__":
    main()
