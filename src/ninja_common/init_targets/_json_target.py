"""Reusable target for MCP hosts that consume ``{mcpServers: {...}}`` JSON config.

Usage — a full target module in 10 lines::

    from ._json_target import target
    from pathlib import Path

    antigravity = target(
        name="antigravity",
        display_name="Google Antigravity",
        config_dir=Path.home() / ".gemini" / "config",
        config_file=Path.home() / ".gemini" / "config" / "mcp_config.json",
        detect_dir=Path.home() / ".gemini",
    )
    detect = antigravity.detect
    install = antigravity.install
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any


if TYPE_CHECKING:
    from collections.abc import Callable

from ninja_common.init_targets._common import (
    atomic_write,
    diff_lines,
    ensure_backup,
    load_mcp_json,
    restore_backup,
)


if TYPE_CHECKING:
    import argparse


class JsonMcpTarget:
    """An install target for any MCP host that uses ``{mcpServers: {...}}`` JSON.

    Attributes
    ----------
    name : str
        CLI subcommand name (e.g. ``"antigravity"``).
    display_name : str
        Human-readable label (e.g. ``"Google Antigravity"``).
    config_dir : Path
        Directory the config file lives in (created if missing).
    config_file : Path
        Full path to the JSON config file (e.g. ``~/.gemini/config/mcp_config.json``).
    detect_dir : Path
        Directory checked by :meth:`detect` — defaults to *config_dir*.
    help_text : str
        Short description shown in ``--help``.
    """

    def __init__(
        self,
        *,
        name: str,
        display_name: str,
        config_dir: Path,
        config_file: Path,
        detect_dir: Path | None = None,
        help_text: str = "",
    ) -> None:
        self.name = name
        self.display_name = display_name
        self.config_dir = config_dir
        self.config_file = config_file
        self.detect_dir = detect_dir or config_dir
        self.help_text = help_text or f"Install into {display_name}"

    # ── public interface ────────────────────────────────────────────────────────

    def detect(self) -> bool:
        """Return ``True`` when *detect_dir* exists (platform is installed)."""
        return self.detect_dir.is_dir()

    def install(self, args: argparse.Namespace) -> int:
        """Merge ninja servers into the target config file.

        Returns 0 on success, non-zero on failure.
        """
        dry_run: bool = getattr(args, "dry_run", False)
        force: bool = getattr(args, "force", False)

        incoming = load_mcp_json()

        existing: dict[str, Any] = {}
        if self.config_file.exists():
            try:
                existing = json.loads(self.config_file.read_text())
            except json.JSONDecodeError as exc:
                print(f"Error: {self.config_file} is not valid JSON: {exc}", file=sys.stderr)
                return 1

        merged, conflicts = self._merge_servers(existing, incoming, force=force)

        if conflicts and not force:
            print(
                f"Error: the following servers already exist in {self.config_file}:\n"
                f"  {', '.join(conflicts)}\n"
                "Pass --force to overwrite them.",
                file=sys.stderr,
            )
            return 1

        before_text = json.dumps(existing, indent=2) if existing else ""
        after_text = json.dumps(merged, indent=2)

        if dry_run:
            print(f"Dry run \u2014 would write to {self.config_file}")
            print()
            if before_text:
                print(diff_lines(before_text + "\n", after_text + "\n", str(self.config_file)))
            else:
                print(after_text)
            return 0

        self.config_dir.mkdir(parents=True, exist_ok=True)
        ensure_backup(self.config_file)

        try:
            atomic_write(self.config_file, after_text + "\n")
        except Exception as exc:
            print(f"Error writing {self.config_file}: {exc}", file=sys.stderr)
            restore_backup(self.config_file)
            return 1

        print(f"Written: {self.config_file}")
        added = [n for n in incoming.get("mcpServers", {}) if n not in conflicts]
        for name in added:
            print(f"  + {name}")
        for name in conflicts:
            print(f"  ~ {name} (skipped \u2014 already exists)")
        return 0

    # ── CLI wiring helpers ──────────────────────────────────────────────────────

    def as_detect_tuple(self) -> tuple[str, Callable[[], bool], str]:
        """Return ``(name, detect_fn, location)`` for the ``detect`` subcommand."""
        try:
            rel = f"~/{self.config_file.relative_to(Path.home())}"
        except ValueError:
            rel = str(self.config_file)
        return (self.name, self.detect, rel)

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        """Attach ``--dry-run`` and ``--force`` flags to *parser*."""
        parser.add_argument(
            "--dry-run",
            action="store_true",
            dest="dry_run",
            help="Print the diff without writing to disk.",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Overwrite servers that already exist in the target file.",
        )

    # ── internals ───────────────────────────────────────────────────────────────

    @staticmethod
    def _merge_servers(
        existing: dict[str, Any],
        incoming: dict[str, Any],
        *,
        force: bool,
    ) -> tuple[dict[str, Any], list[str]]:
        """Merge ``mcpServers`` from *incoming* into *existing*.

        Returns ``(merged_dict, conflict_names)`` where *conflict_names* are
        server keys that already existed and were **not** overwritten.
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


def target(
    name: str,
    display_name: str,
    config_dir: Path,
    config_file: Path,
    *,
    detect_dir: Path | None = None,
    help_text: str = "",
) -> JsonMcpTarget:
    """Convenience factory that creates a :class:`JsonMcpTarget`."""
    return JsonMcpTarget(
        name=name,
        display_name=display_name,
        config_dir=config_dir,
        config_file=config_file,
        detect_dir=detect_dir,
        help_text=help_text,
    )
