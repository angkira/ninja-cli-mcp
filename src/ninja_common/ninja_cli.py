"""ninja-mcp — unified CLI for all ninja MCP tools.

Usage::

    ninja-mcp init <target>     Install MCP servers into a host config
    ninja-mcp config            Configuration manager
    ninja-mcp daemon            Daemon process manager
    ninja-mcp skill             Skill packaging
    ninja-mcp hooks coder       Coder git hooks
    ninja-mcp hooks secretary   Secretary repository hooks
    ninja-mcp version           Show version
"""

from __future__ import annotations

import importlib
import sys
from typing import NoReturn


# ── subcommand registry ────────────────────────────────────────────────────────

_SUBCOMMANDS: dict[str, str] = {
    "init": "ninja_common.init_cli",
    "config": "ninja_common.config_cli",
    "daemon": "ninja_common.daemon",
    "skill": "ninja_common.skill_cli",
}

# Commands whose downstream module expects the command name to remain
# in ``sys.argv[1]`` because the module defines its own top-level subparser
# matching that command.
_KEEP_COMMAND: set[str] = {"init"}


def main() -> NoReturn:
    """Unified entry point — dispatch to the right sub-module."""
    if len(sys.argv) < 2:
        _print_usage()
        sys.exit(1)

    command = sys.argv[1]

    # ── built-in commands ───────────────────────────────────────────────────
    if command in ("-h", "--help", "help"):
        _print_usage()
        sys.exit(0)

    if command == "version":
        _print_version()
        sys.exit(0)

    if command == "hooks":
        _delegate_hooks()
        sys.exit(0)

    # ── dispatch to registered subcommands ──────────────────────────────────
    if command in _SUBCOMMANDS:
        _delegate(_SUBCOMMANDS[command], command)
        sys.exit(0)

    print(f"ninja-mcp: unknown command: {command}", file=sys.stderr)
    print(file=sys.stderr)
    _print_usage()
    sys.exit(1)


# ── delegation ────────────────────────────────────────────────────────────────


def _delegate(module_path: str, command: str) -> None:
    """Import *module_path* and call its ``main()``.

    For commands in ``_KEEP_COMMAND`` the module sees ``sys.argv`` with
    the command name preserved in position 1 (e.g. ``['ninja-mcp', 'init',
    'detect']``).  Otherwise the command is stripped so the module only
    sees its own arguments (e.g. ``['ninja-mcp config', 'configure']``).
    """
    mod = importlib.import_module(module_path)
    orig_argv = sys.argv

    if command in _KEEP_COMMAND:
        prog = "ninja-mcp"
        sys.argv = [prog, *orig_argv[1:]]
    else:
        prog = f"ninja-mcp {command}"
        sys.argv = [prog, *orig_argv[2:]]

    exit_code = 0
    try:
        result = mod.main()
        if isinstance(result, int):
            exit_code = result
    except SystemExit as exc:
        exit_code = exc.code if isinstance(exc.code, int) else 1
    finally:
        sys.argv = orig_argv

    if exit_code:
        sys.exit(exit_code)


# ── hooks ─────────────────────────────────────────────────────────────────────


def _delegate_hooks() -> None:
    """Handle ``ninja-mcp hooks <kind> <args>``."""
    if len(sys.argv) < 3 or sys.argv[2] in ("-h", "--help", "help"):
        print("Usage: ninja-mcp hooks {coder|secretary} <args>", file=sys.stderr)
        print()
        print("  hooks coder       Code quality hooks (format, lint, pre-commit)")
        print("  hooks secretary   Repository hooks (validate-path, session-report, ...)")
        sys.exit(1)

    kind = sys.argv[2]
    module_map = {
        "coder": "ninja_coder.hooks_cli",
        "secretary": "ninja_secretary.hooks_cli",
    }

    if kind not in module_map:
        print(f"ninja-mcp hooks: unknown hook kind: {kind}", file=sys.stderr)
        print("  Available: coder, secretary", file=sys.stderr)
        sys.exit(1)

    orig_argv = sys.argv
    sys.argv = [f"ninja-mcp hooks {kind}", *orig_argv[3:]]
    try:
        _delegate(module_map[kind], kind)
    finally:
        sys.argv = orig_argv


# ── built-in helpers ──────────────────────────────────────────────────────────


def _print_usage() -> None:
    """Print top-level help text."""
    print("Usage: ninja-mcp <command> [options]")
    print()
    print("Commands:")
    print("  init <host>     Install MCP servers into a host config file")
    print("  config          Interactive configuration TUI (default)")
    print("  daemon          Daemon process manager")
    print("  skill           Skill packaging")
    print("  hooks coder     Code quality hooks (format, lint, pre-commit)")
    print("  hooks secretary Repository hooks (validate-path, session-report, ...)")
    print("  version         Show version")
    print()
    print("Run 'ninja-mcp <command> --help' for command-specific help.")
    print()
    print("Examples:")
    print("  ninja-mcp init detect")
    print("  ninja-mcp init antigravity --dry-run")
    print("  ninja-mcp config              # launch interactive TUI")
    print("  ninja-mcp daemon status")
    print("  ninja-mcp skill package my-skill")


def _print_version() -> None:
    """Print installed version."""
    try:
        from importlib.metadata import version as get_version

        v = get_version("ninja-mcp")
    except Exception:
        v = "unknown"
    print(f"ninja-mcp {v}")


if __name__ == "__main__":
    main()
