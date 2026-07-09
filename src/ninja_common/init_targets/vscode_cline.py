"""Install target: VS Code Cline / Continue (~/.config/Code/User/mcp.json)."""

from __future__ import annotations

from pathlib import Path

from ninja_common.init_targets._json_target import target


vscode_cline = target(
    name="vscode-cline",
    display_name="VS Code (Cline / Continue)",
    config_dir=Path.home() / ".config" / "Code" / "User",
    config_file=Path.home() / ".config" / "Code" / "User" / "mcp.json",
    detect_dir=Path.home() / ".config" / "Code",
)
detect = vscode_cline.detect
install = vscode_cline.install
