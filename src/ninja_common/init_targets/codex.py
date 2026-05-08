"""Install target: OpenAI Codex CLI (~/.codex/config.toml)."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ninja_common.init_targets._common import (
    atomic_write,
    diff_lines,
    ensure_backup,
    load_codex_toml_text,
    restore_backup,
)


if TYPE_CHECKING:
    import argparse

_CODEX_DIR = Path.home() / ".codex"
_CONFIG_FILE = _CODEX_DIR / "config.toml"

# The section keys that ninja adds (tomlkit table names).
_NINJA_SECTIONS = [
    "mcp_servers.ninja_coder",
    "mcp_servers.ninja_researcher",
    "mcp_servers.ninja_secretary",
]


def detect() -> bool:
    """Return True when ~/.codex/ exists (Codex CLI is installed)."""
    return _CODEX_DIR.is_dir()


def _existing_sections(doc: Any) -> list[str]:
    """Return dotted section names already present in *doc*."""
    import tomlkit

    found: list[str] = []
    mcp = doc.get("mcp_servers")
    if isinstance(mcp, (dict, tomlkit.container.Container)):
        for key in mcp:
            found.append(f"mcp_servers.{key}")
    return found


def _merge_toml(existing_text: str, incoming_text: str) -> tuple[str, list[str]]:
    """Merge the ninja sections from *incoming_text* into *existing_text*.

    Uses tomlkit for round-trip safety (preserves comments).
    Returns ``(merged_text, conflicts)`` where *conflicts* are section names
    that already existed in the target.
    """
    import tomlkit

    existing_doc = tomlkit.parse(existing_text)
    incoming_doc = tomlkit.parse(incoming_text)

    present = _existing_sections(existing_doc)
    conflicts: list[str] = []

    incoming_servers = incoming_doc.get("mcp_servers", {})
    if not isinstance(existing_doc.get("mcp_servers"), dict):
        existing_doc["mcp_servers"] = tomlkit.table()

    for key, value in incoming_servers.items():
        dotted = f"mcp_servers.{key}"
        if dotted in present:
            conflicts.append(dotted)
        else:
            existing_doc["mcp_servers"][key] = value  # type: ignore[index]

    return tomlkit.dumps(existing_doc), conflicts


def install(args: argparse.Namespace) -> int:
    """Merge ninja servers into ~/.codex/config.toml.

    Returns 0 on success, non-zero on failure.
    """
    dry_run: bool = getattr(args, "dry_run", False)
    force: bool = getattr(args, "force", False)

    try:
        import importlib

        importlib.import_module("tomlkit")
    except ImportError:
        print(
            "Error: tomlkit is required for the codex target.\n"
            "Install it with: pip install tomlkit>=0.13",
            file=sys.stderr,
        )
        return 1

    incoming_text = load_codex_toml_text()

    existing_text = ""
    if _CONFIG_FILE.exists():
        existing_text = _CONFIG_FILE.read_text(encoding="utf-8")

    merged_text, conflicts = _merge_toml(existing_text or "\n", incoming_text)

    if conflicts and not force:
        print(
            f"Error: the following sections already exist in {_CONFIG_FILE}:\n"
            + "".join(f"  [{s}]\n" for s in conflicts)
            + "Pass --force to overwrite them.",
            file=sys.stderr,
        )
        return 1

    if force and conflicts:
        # Re-merge with existing sections replaced
        import tomlkit

        existing_doc = tomlkit.parse(existing_text or "\n")
        incoming_doc = tomlkit.parse(incoming_text)
        incoming_servers = incoming_doc.get("mcp_servers", {})
        if not isinstance(existing_doc.get("mcp_servers"), dict):
            existing_doc["mcp_servers"] = tomlkit.table()
        for key, value in incoming_servers.items():
            existing_doc["mcp_servers"][key] = value  # type: ignore[index]
        merged_text = tomlkit.dumps(existing_doc)
        conflicts = []  # all overwritten

    if dry_run:
        print(f"Dry run — would write to {_CONFIG_FILE}")
        print()
        if existing_text:
            print(diff_lines(existing_text, merged_text, str(_CONFIG_FILE)))
        else:
            print(merged_text)
        return 0

    _CODEX_DIR.mkdir(parents=True, exist_ok=True)
    ensure_backup(_CONFIG_FILE)

    try:
        atomic_write(_CONFIG_FILE, merged_text)
    except Exception as exc:
        print(f"Error writing {_CONFIG_FILE}: {exc}", file=sys.stderr)
        restore_backup(_CONFIG_FILE)
        return 1

    print(f"Written: {_CONFIG_FILE}")
    for section in _NINJA_SECTIONS:
        if section not in conflicts:
            print(f"  + [{section}]")
    for section in conflicts:
        print(f"  ~ [{section}] (skipped — already exists)")
    return 0
