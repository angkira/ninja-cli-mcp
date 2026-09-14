from __future__ import annotations

import json
import subprocess
import sys
from importlib.metadata import PackageNotFoundError
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

from ninja_config import modern_tui
from ninja_config.auto_updater import AutoUpdater, UpdateError
from ninja_config.modern_tui import NinjaConfigApp


if TYPE_CHECKING:
    from pathlib import Path


def test_package_update_pypi_uses_uv_when_installed_as_uv_tool(tmp_path: Path) -> None:
    """PyPI channel for a uv-tool install: reinstall via uv tool install."""
    updater = AutoUpdater(repo_path=tmp_path, channel="pypi")

    with (
        patch.object(AutoUpdater, "_install_method", return_value="uv-tool"),
        patch("ninja_config.auto_updater.subprocess.run") as run,
    ):
        run.return_value = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout="Installed 9 executables",
            stderr="",
        )

        updater._reinstall_package()

    command = run.call_args.args[0]
    assert command == ["uv", "tool", "install", "--force", "ninja-mcp[runtime]"]


def test_package_update_pypi_uses_pip_when_installed_with_pip(tmp_path: Path) -> None:
    """PyPI channel for a pip install: upgrade through pip --user."""
    updater = AutoUpdater(repo_path=tmp_path, channel="pypi")

    with (
        patch.object(AutoUpdater, "_install_method", return_value="pip"),
        patch("ninja_config.auto_updater.subprocess.run") as run,
    ):
        run.return_value = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout="",
            stderr="",
        )

        updater._reinstall_package()

    command = run.call_args.args[0]
    assert command[:6] == [sys.executable, "-m", "pip", "install", "--user", "--upgrade"]
    assert command[-1] == "ninja-mcp[runtime]"


def test_package_update_pypi_uses_pipx(tmp_path: Path) -> None:
    """PyPI channel for a pipx install: upgrade through pipx."""
    updater = AutoUpdater(repo_path=tmp_path, channel="pypi")

    with (
        patch.object(AutoUpdater, "_install_method", return_value="pipx"),
        patch("ninja_config.auto_updater.subprocess.run") as run,
    ):
        run.return_value = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
        updater._reinstall_package()

    assert run.call_args.args[0] == ["pipx", "install", "--force", "ninja-mcp[runtime]"]


def test_pip_retries_with_break_system_packages(tmp_path: Path) -> None:
    """Externally-managed (PEP 668) pip failure is retried with the override."""
    updater = AutoUpdater(repo_path=tmp_path, channel="pypi")
    calls: list[list[str]] = []

    def fake_run(cmd, **_kw):
        calls.append(cmd)
        if "--break-system-packages" not in cmd:
            raise subprocess.CalledProcessError(
                1, cmd, output="", stderr="error: externally-managed-environment"
            )
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="ok", stderr="")

    with (
        patch.object(AutoUpdater, "_install_method", return_value="pip"),
        patch("ninja_config.auto_updater.subprocess.run", side_effect=fake_run),
    ):
        updater._reinstall_package()

    assert any("--break-system-packages" in c for c in calls)


def test_package_update_github_without_repo_uses_uv_tool_install(tmp_path: Path) -> None:
    """Github channel without any checkout: install the PyPI build via uv."""
    updater = AutoUpdater(repo_path=tmp_path, channel="github")

    with (
        patch("ninja_config.auto_updater.subprocess.run") as run,
        patch.object(AutoUpdater, "_find_editable_repo", return_value=None) as _editable,
    ):
        run.return_value = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout="Installed 9 executables",
            stderr="",
        )

        updater._reinstall_package()

    command = run.call_args.args[0]
    assert command == ["uv", "tool", "install", "--force", "ninja-mcp[runtime]"]


def test_package_update_editable_uses_uv_tool_install(tmp_path: Path) -> None:
    """Github channel with editable install: reinstall from the source checkout via uv."""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "pyproject.toml").write_text("[project]\nname = 'ninja-mcp'\n")

    updater = AutoUpdater(repo_path=tmp_path, channel="github")

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


def test_package_update_github_pulls_and_reinstalls_checkout(tmp_path: Path) -> None:
    """Github channel with a plain git checkout: pull, then reinstall it editable."""
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    (checkout / ".git").mkdir()

    updater = AutoUpdater(repo_path=checkout, channel="github")

    with (
        patch("ninja_config.auto_updater.subprocess.run") as run,
        patch.object(AutoUpdater, "_find_editable_repo", return_value=None) as _editable,
    ):
        run.return_value = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout="ok",
            stderr="",
        )

        updater._reinstall_package()

    commands = [call.args[0] for call in run.call_args_list]
    assert commands[0] == ["git", "pull"]
    assert commands[1][0:4] == ["uv", "tool", "install", "--force"]
    assert "--editable" in commands[1]
    assert str(checkout) in commands[1]


def test_package_update_brew_runs_update_and_upgrade(tmp_path: Path) -> None:
    """Brew channel: refresh brew itself, then upgrade the formula."""
    updater = AutoUpdater(repo_path=tmp_path, channel="brew")

    with patch("ninja_config.auto_updater.subprocess.run") as run:
        run.return_value = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout="ok",
            stderr="",
        )

        updater._reinstall_package()

    commands = [call.args[0] for call in run.call_args_list]
    assert commands[0] == ["brew", "update"]
    assert commands[1] == ["brew", "upgrade", "ninja-mcp"]


def test_package_update_rejects_unknown_channel(tmp_path: Path) -> None:
    """An unknown channel fails fast with a clear error."""
    updater = AutoUpdater(repo_path=tmp_path, channel="gitlab")

    with pytest.raises(UpdateError, match="Unknown channel"):
        updater._reinstall_package()


def test_resolve_channel_returns_explicit_channel(tmp_path: Path) -> None:
    """Explicit channels are returned as-is once validated."""
    updater = AutoUpdater(repo_path=tmp_path, channel="pypi")

    assert updater.resolve_channel() == "pypi"


def test_resolve_channel_rejects_unknown_channel(tmp_path: Path) -> None:
    """Unknown explicit channels raise an UpdateError."""
    updater = AutoUpdater(repo_path=tmp_path, channel="snap")

    with pytest.raises(UpdateError, match="Unknown channel 'snap'"):
        updater.resolve_channel()


def test_detect_channel_prefers_source_checkout(tmp_path: Path) -> None:
    """A git checkout or editable install resolves to the github channel."""
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    (checkout / ".git").mkdir()

    updater = AutoUpdater(repo_path=checkout, channel="auto")

    with patch.object(AutoUpdater, "_find_editable_repo", return_value=None) as _editable:
        assert updater._detect_channel() == "github"


def test_detect_channel_uses_brew_when_formula_installed(tmp_path: Path) -> None:
    """A Homebrew-managed install resolves to the brew channel."""
    updater = AutoUpdater(repo_path=tmp_path, channel="auto")

    with (
        patch.object(AutoUpdater, "_find_editable_repo", return_value=None) as _editable,
        patch("ninja_config.auto_updater.shutil.which", return_value="/opt/homebrew/bin/brew"),
        patch.object(AutoUpdater, "_brew_has_formula", return_value=True),
    ):
        assert updater._detect_channel() == "brew"


def test_detect_channel_falls_back_to_pypi(tmp_path: Path) -> None:
    """Without checkout or brew, the pypi channel is used."""
    updater = AutoUpdater(repo_path=tmp_path, channel="auto")

    with (
        patch.object(AutoUpdater, "_find_editable_repo", return_value=None) as _editable,
        patch("ninja_config.auto_updater.shutil.which", return_value=None),
    ):
        assert updater._detect_channel() == "pypi"


def test_brew_has_formula_handles_missing_brew(tmp_path: Path) -> None:
    """A missing brew binary is reported as no formula, not an error."""
    updater = AutoUpdater(repo_path=tmp_path)

    with patch("ninja_config.auto_updater.subprocess.run", side_effect=OSError):
        assert updater._brew_has_formula() is False


def test_installed_version_defaults_when_not_installed() -> None:
    """A missing installation reports a dev placeholder version."""
    updater = AutoUpdater(repo_path=None)

    with (
        patch("ninja_config.auto_updater.pkg_version", side_effect=PackageNotFoundError),
        patch("ninja_agent.__version__", None),
    ):
        assert updater._installed_version() == "0.0.0-dev"


def test_installed_version_falls_back_to_agent_version() -> None:
    """When package metadata is missing the agent module version is used."""
    updater = AutoUpdater(repo_path=None)

    with (
        patch("ninja_config.auto_updater.pkg_version", side_effect=PackageNotFoundError),
        patch("ninja_agent.__version__", "1.0.3"),
    ):
        assert updater._installed_version() == "1.0.3"


def test_needs_update_compares_pep440_versions() -> None:
    """Version comparison follows PEP 440 ordering."""
    updater = AutoUpdater(repo_path=None)

    assert updater._needs_update("1.0.0", "1.1.0") is True
    assert updater._needs_update("1.2.0", "1.2.0") is False
    assert updater._needs_update("1.3.0", "1.2.0") is False


def test_needs_update_defaults_to_true_on_invalid_version() -> None:
    """Unparseable versions conservatively report an update as needed."""
    updater = AutoUpdater(repo_path=None)

    assert updater._needs_update("1.0.0", "not-a-version") is True


def test_update_skips_steps_when_up_to_date(tmp_path: Path) -> None:
    """When the latest version matches the installed one, no update steps run."""
    updater = AutoUpdater(repo_path=tmp_path, channel="pypi")

    with (
        patch.object(AutoUpdater, "_installed_version", return_value="1.0.0"),
        patch.object(AutoUpdater, "_pypi_latest", return_value="1.0.0"),
        patch.object(AutoUpdater, "_reinstall_package") as reinstall,
    ):
        result = updater.update()

    assert result["up_to_date"] is True
    assert result["verified"] is True
    assert result["channel"] == "pypi"
    assert result["steps_completed"] == []
    reinstall.assert_not_called()


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
