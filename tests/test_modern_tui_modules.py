"""Tests for the Modules tab helpers on NinjaConfigApp (no event loop)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ninja_common.defaults import DEFAULT_ENABLED_MODULES
from ninja_config.modern_tui import DaemonRow, ModuleRow, NinjaConfigApp


if TYPE_CHECKING:
    from pathlib import Path


def _make_app(tmp_path: Path) -> NinjaConfigApp:
    """Create a NinjaConfigApp backed by a temp config file."""
    return NinjaConfigApp(config_path=str(tmp_path / ".ninja-mcp.env"))


def test_enabled_modules_parses_config(tmp_path: Path) -> None:
    """Comma-separated NINJA_ENABLED_MODULES is parsed into a module list."""
    app = _make_app(tmp_path)
    app.config_manager.set("NINJA_ENABLED_MODULES", "coder,agent")

    assert app._enabled_modules() == ["coder", "agent"]


def test_enabled_modules_falls_back_to_default(tmp_path: Path) -> None:
    """Missing NINJA_ENABLED_MODULES falls back to DEFAULT_ENABLED_MODULES."""
    app = _make_app(tmp_path)

    assert app._enabled_modules() == list(DEFAULT_ENABLED_MODULES)


def test_set_enabled_modules_writes(tmp_path: Path) -> None:
    """_set_enabled_modules persists a comma-separated value to config."""
    app = _make_app(tmp_path)

    app._set_enabled_modules(["coder", "researcher", "agent"])

    assert app.config_manager.get("NINJA_ENABLED_MODULES") == "coder,researcher,agent"


def test_module_row_exposes_module_name() -> None:
    """ModuleRow identifies its module for the inline toggle/install handlers."""
    assert ModuleRow("agent").module_name == "agent"


def test_daemon_row_exposes_module_name() -> None:
    """DaemonRow identifies its module for the inline start/stop toggle."""
    assert DaemonRow("coder").module_name == "coder"
