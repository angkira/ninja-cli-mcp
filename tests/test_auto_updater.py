from __future__ import annotations

import json
import subprocess
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

from ninja_config import modern_tui
from ninja_config.auto_updater import AutoUpdater
from ninja_config.modern_tui import NinjaConfigApp


if TYPE_CHECKING:
    from pathlib import Path


def test_package_update_uses_ninja_mcp_daemon_upgrade(tmp_path: Path) -> None:
    """Non-editable install: the updater uses the daemon upgrade entrypoint."""
    updater = AutoUpdater(repo_path=tmp_path)

    with (
        patch("ninja_config.auto_updater.subprocess.run") as run,
        patch.object(AutoUpdater, "_find_editable_repo", return_value=None) as _editable,
    ):
        run.return_value = subprocess.CompletedProcess(
            args=["ninja-mcp", "daemon", "upgrade"],
            returncode=0,
            stdout="ok",
            stderr="",
        )

        updater._reinstall_package()

    command = run.call_args.args[0]
    assert command == ["ninja-mcp", "daemon", "upgrade"]
    assert "uv" not in command


def test_package_update_editable_uses_uv_tool_install(tmp_path: Path) -> None:
    """Editable install: the updater reinstalls from the source checkout via uv."""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "pyproject.toml").write_text("[project]\nname = 'ninja-mcp'\n")

    updater = AutoUpdater(repo_path=tmp_path)

    with (
        patch("ninja_config.auto_updater.subprocess.run") as run,
        patch.object(AutoUpdater, "_find_editable_repo", return_value=repo) as _editable,
    ):
        run.return_value = subprocess.CompletedProcess(
            args=["uv", "tool", "install", "--force", "--editable", str(repo)],
            returncode=0,
            stdout="Installed 9 executables",
            stderr="",
        )

        updater._reinstall_package()

    command = run.call_args.args[0]
    assert command[0:4] == ["uv", "tool", "install", "--force"]
    assert "--editable" in command
    assert str(repo) in command
    assert "." not in command


def test_find_editable_repo_detects_real_layout() -> None:
    """On a machine with an editable install the repo root is returned."""
    found = AutoUpdater(repo_path=None)._find_editable_repo()
    assert found is None or found.name == "ninja-cli-mcp"


def test_restart_daemons_uses_unified_ninja_mcp_entrypoint(tmp_path: Path) -> None:
    """Daemon restart should go through ninja-mcp, not the legacy ninja-daemon binary."""
    updater = AutoUpdater(repo_path=tmp_path)

    with patch("ninja_config.auto_updater.subprocess.run") as run:
        run.return_value = subprocess.CompletedProcess(
            args=["ninja-mcp", "daemon", "restart"],
            returncode=0,
            stdout="ok",
            stderr="",
        )

        updater._restart_daemons()

    assert run.call_args.args[0] == ["ninja-mcp", "daemon", "restart"]


def test_verify_accepts_coder_and_researcher_daemons(tmp_path: Path) -> None:
    """The supported default install is healthy when coder and researcher are running."""
    updater = AutoUpdater(repo_path=tmp_path)
    status = {
        "coder": {"running": True},
        "researcher": {"running": True},
        "secretary": {"running": False},
    }

    with (
        patch("ninja_config.auto_updater.subprocess.run") as run,
        patch("ninja_config.auto_updater.CredentialManager") as manager_cls,
    ):
        run.return_value = subprocess.CompletedProcess(
            args=["ninja-mcp", "daemon", "status"],
            returncode=0,
            stdout=json.dumps(status),
            stderr="",
        )
        manager = MagicMock()
        manager.get.return_value = "present"
        manager_cls.return_value = manager

        result = updater._verify()

    assert run.call_args.args[0] == ["ninja-mcp", "daemon", "status"]
    assert result["success"] is True
    assert result["checks"]["daemons"]["running"] == ["coder", "researcher"]


def test_modern_tui_update_hint_uses_ninja_mcp_entrypoint() -> None:
    """The TUI should point users at the managed updater."""

    class FakeApp:
        def __init__(self) -> None:
            self.messages: list[str] = []

        def notify(self, message: str, timeout: int = 0) -> None:
            self.messages.append(message)

    app = FakeApp()

    NinjaConfigApp._check_update(app)  # type: ignore[arg-type]

    assert not hasattr(modern_tui, "subprocess")
    assert app.messages == ["Update with: ninja-mcp update"]
