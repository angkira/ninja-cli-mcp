"""Tests for the Modules tab helpers on NinjaConfigApp (no event loop)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING

from ninja_common.defaults import DEFAULT_ENABLED_MODULES
from ninja_config.modern_tui import NinjaConfigApp


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


def test_selected_module_uses_highlighted_child(tmp_path: Path) -> None:
    """_selected_module reads module_name from the highlighted list row."""
    app = _make_app(tmp_path)
    list_view = SimpleNamespace(highlighted_child=SimpleNamespace(module_name="agent"))
    app.query_one = lambda *args, **kwargs: list_view  # type: ignore[method-assign]

    assert app._selected_module() == "agent"


def test_selected_module_none_when_empty(tmp_path: Path) -> None:
    """Highlighted rows without a module_name attribute yield None."""
    app = _make_app(tmp_path)
    list_view = SimpleNamespace(highlighted_child=SimpleNamespace())
    app.query_one = lambda *args, **kwargs: list_view  # type: ignore[method-assign]

    assert app._selected_module() is None
