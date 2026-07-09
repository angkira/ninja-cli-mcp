"""Install target: Roo Code (~/.config/roo/mcp_settings.json)."""

from __future__ import annotations

from pathlib import Path

from ninja_common.init_targets._json_target import target


roo_code = target(
    name="roo-code",
    display_name="Roo Code",
    config_dir=Path.home() / ".config" / "roo",
    config_file=Path.home() / ".config" / "roo" / "mcp_settings.json",
    detect_dir=Path.home() / ".config" / "roo",
)
detect = roo_code.detect
install = roo_code.install
