"""Tests for the Modules tab helpers on NinjaConfigApp (no event loop)."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import patch

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


def test_which_binary_finds_binary_off_path(tmp_path: Path, monkeypatch) -> None:
    """A CLI installed in ~/.local/bin is found even when not on PATH."""
    from ninja_config.model_selector import OPERATORS, _which_binary

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr("ninja_config.model_selector.shutil.which", lambda _n: None)
    tool = tmp_path / ".local" / "bin" / "mytool"
    tool.parent.mkdir(parents=True)
    tool.write_text("#!/bin/sh\n")
    tool.chmod(0o755)

    assert _which_binary("mytool") == str(tool)
    assert any(op.id == "codex" for op in OPERATORS)


def test_operator_select_options_lists_every_operator(tmp_path: Path, monkeypatch) -> None:
    """The picker lists all known operators, labelling the uninstalled ones."""
    from ninja_config.model_selector import OPERATORS

    app = _make_app(tmp_path)
    monkeypatch.setattr(NinjaConfigApp, "_installed_operators", lambda _self: [])

    options = app._operator_select_options("NINJA_CODE_BIN")

    assert {value for _, value in options} == {op.id for op in OPERATORS}
    assert all("not installed" in label for label, _ in options)


def test_daemon_cli_delegates_to_cli_subprocess(tmp_path: Path) -> None:
    """Daemon start/stop go through the CLI, never an in-process fork."""
    import subprocess

    app = _make_app(tmp_path)
    with patch("subprocess.run") as run:
        run.return_value = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
        ok, detail = app._daemon_cli("start", "coder")

    assert (ok, detail) == (True, "")
    assert run.call_args.args[0] == ["ninja-mcp", "daemon", "start", "coder"]


def test_daemon_cli_reports_failure(tmp_path: Path) -> None:
    """A non-zero daemon CLI exit yields (False, last stderr line)."""
    import subprocess

    app = _make_app(tmp_path)
    with patch("subprocess.run") as run:
        run.return_value = subprocess.CompletedProcess(
            args=[], returncode=1, stdout="", stderr="boom: no such module\n"
        )
        ok, detail = app._daemon_cli("start", "nope")

    assert ok is False
    assert detail == "boom: no such module"
