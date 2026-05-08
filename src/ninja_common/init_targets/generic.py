"""Install target: generic MCP hosts (Windsurf, Claude Desktop, VS Code Copilot, etc.)."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from ninja_common.init_targets._common import load_mcp_json


if TYPE_CHECKING:
    import argparse
    from pathlib import Path


def detect() -> bool:
    """Return True when the generic target is always applicable."""
    return True


def install(args: argparse.Namespace) -> int:
    """Print dist/mcp.json to stdout with a placement comment.

    Returns 0 on success.
    """
    _ = args  # generic has no flags beyond what argparse provides
    data = load_mcp_json()
    header = (
        "# ninja-mcp — generic MCP configuration\n"
        "# Paste the JSON below into the mcpServers block of:\n"
        "#   Windsurf:         ~/.windsurf/mcp.json\n"
        "#   Claude Desktop:   ~/Library/Application Support/Claude/claude_desktop_config.json\n"
        "#   VS Code Copilot:  .vscode/mcp.json  (workspace) or user settings\n"
        "#   Any MCP host:     the host's mcp.json / settings.json mcpServers section\n"
    )
    print(header)
    print(json.dumps(data, indent=2))
    return 0


def _find_dist_mcp_json() -> Path:
    """Return the resolved path to dist/mcp.json (used by tests)."""
    from ninja_common.init_targets._common import _dist_path

    return _dist_path("mcp.json")
