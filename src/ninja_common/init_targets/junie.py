"""Install target: Junie (~/.junie/mcp/mcp.json)."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from ninja_common.init_targets._json_target import JsonMcpTarget


if TYPE_CHECKING:
    import argparse

config_dir = Path.home() / ".junie" / "mcp"
config_file = config_dir / "mcp.json"
detect_dir = Path.home() / ".junie"
help_text = "Merge into ~/.junie/mcp/mcp.json."


class _JunieTarget(JsonMcpTarget):
    @property
    def config_dir(self) -> Path:  # type: ignore[override]
        return config_dir

    @config_dir.setter
    def config_dir(self, val: Path) -> None:
        global config_dir
        config_dir = val

    @property
    def config_file(self) -> Path:  # type: ignore[override]
        return config_file

    @config_file.setter
    def config_file(self, val: Path) -> None:
        global config_file
        config_file = val

    @property
    def detect_dir(self) -> Path:  # type: ignore[override]
        return detect_dir

    @detect_dir.setter
    def detect_dir(self, val: Path) -> None:
        global detect_dir
        detect_dir = val


junie = _JunieTarget(
    name="junie",
    display_name="Junie",
    config_dir=config_dir,
    config_file=config_file,
    detect_dir=detect_dir,
    help_text=help_text,
)


def detect() -> bool:
    """Return True when ~/.junie/ exists (Junie is installed)."""
    return detect_dir.is_dir()


def install(args: argparse.Namespace) -> int:
    """Merge ninja servers into ~/.junie/mcp/mcp.json."""
    return junie.install(args)
