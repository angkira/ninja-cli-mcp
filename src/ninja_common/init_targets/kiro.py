"""Install target: Kiro IDE (~/.kiro/settings/mcp.json)."""

from __future__ import annotations

from pathlib import Path

from ninja_common.init_targets._json_target import target


kiro = target(
    name="kiro",
    display_name="Kiro IDE",
    config_dir=Path.home() / ".kiro" / "settings",
    config_file=Path.home() / ".kiro" / "settings" / "mcp.json",
    detect_dir=Path.home() / ".kiro",
)
detect = kiro.detect
install = kiro.install
