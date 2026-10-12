"""Install target: Pi coding agent (~/.pi/agent/mcp.json)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ninja_common.init_targets._json_target import JsonMcpTarget


if TYPE_CHECKING:
    import argparse

_agent_dir = Path(os.environ.get("PI_CODING_AGENT_DIR", Path.home() / ".pi" / "agent"))
config_dir = _agent_dir
config_file = config_dir / "mcp.json"
detect_dir = Path.home() / ".pi"
help_text = "Merge into ~/.pi/agent/mcp.json."


class _PiTarget(JsonMcpTarget):
    @property
    def config_dir(self) -> Path:
        return config_dir

    @config_dir.setter
    def config_dir(self, val: Path) -> None:
        global config_dir
        config_dir = val

    @property
    def config_file(self) -> Path:
        return config_file

    @config_file.setter
    def config_file(self, val: Path) -> None:
        global config_file
        config_file = val

    @property
    def detect_dir(self) -> Path:
        return detect_dir

    @detect_dir.setter
    def detect_dir(self, val: Path) -> None:
        global detect_dir
        detect_dir = val

    @staticmethod
    def _merge_servers(
        existing: dict[str, Any],
        incoming: dict[str, Any],
        *,
        force: bool,
    ) -> tuple[dict[str, Any], list[str]]:
        """Merge incoming servers with exposure='direct' for Pi."""
        direct_incoming = {
            "mcpServers": {
                name: {**cfg, "exposure": "direct"}
                for name, cfg in incoming.get("mcpServers", {}).items()
            }
        }
        return JsonMcpTarget._merge_servers(existing, direct_incoming, force=force)


pi = _PiTarget(
    name="pi",
    display_name="Pi",
    config_dir=config_dir,
    config_file=config_file,
    detect_dir=detect_dir,
    help_text=help_text,
)


def detect() -> bool:
    """Return True when ~/.pi/ exists (Pi is installed)."""
    return detect_dir.is_dir()


def install(args: argparse.Namespace) -> int:
    """Merge ninja servers into ~/.pi/agent/mcp.json."""
    return pi.install(args)
