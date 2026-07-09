"""Install target: Google Antigravity IDE (~/.gemini/config/mcp_config.json)."""

from __future__ import annotations

from pathlib import Path

from ninja_common.init_targets._json_target import target


antigravity = target(
    name="antigravity",
    display_name="Google Antigravity",
    config_dir=Path.home() / ".gemini" / "config",
    config_file=Path.home() / ".gemini" / "config" / "mcp_config.json",
    detect_dir=Path.home() / ".gemini",
)
detect = antigravity.detect
install = antigravity.install
