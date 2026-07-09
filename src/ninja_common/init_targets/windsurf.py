"""Install target: Windsurf / Devin Desktop (~/.windsurf/mcp.json)."""

from __future__ import annotations

from pathlib import Path

from ninja_common.init_targets._json_target import target


windsurf = target(
    name="windsurf",
    display_name="Windsurf (Devin Desktop)",
    config_dir=Path.home() / ".windsurf",
    config_file=Path.home() / ".windsurf" / "mcp.json",
    detect_dir=Path.home() / ".windsurf",
)
detect = windsurf.detect
install = windsurf.install
