"""Tests for DaemonManager enabled-module config persistence."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ninja_common.config_manager import ConfigManager
from ninja_common.daemon import DaemonManager


if TYPE_CHECKING:
    from pathlib import Path


def _make_manager(tmp_path: Path) -> DaemonManager:
    """Create a DaemonManager whose cache dir lives under tmp_path."""
    return DaemonManager(cache_dir=tmp_path / ".cache" / "ninja-mcp")


def test_save_updates_both_plain_and_export_lines(tmp_path: Path, monkeypatch) -> None:
    """Saving rewrites both plain and export lines while preserving comments."""
    monkeypatch.setenv("HOME", str(tmp_path))
    env = tmp_path / ".ninja-mcp.env"
    env.write_text(
        "# ninja config\n"
        "\n"
        "NINJA_ENABLED_MODULES=coder,researcher\n"
        "# trailing comment\n"
        "export NINJA_ENABLED_MODULES='coder,researcher'\n"
    )
    dm = _make_manager(tmp_path)

    dm._save_enabled_modules(["coder", "researcher", "agent"])

    text = env.read_text()
    assert "NINJA_ENABLED_MODULES=coder,researcher,agent" in text
    assert "export NINJA_ENABLED_MODULES='coder,researcher,agent'" in text
    assert "# ninja config" in text
    assert "# trailing comment" in text
    assert ConfigManager(str(env)).get("NINJA_ENABLED_MODULES") == "coder,researcher,agent"


def test_save_appends_when_key_missing(tmp_path: Path, monkeypatch) -> None:
    """Saving appends the key when the env file does not declare it."""
    monkeypatch.setenv("HOME", str(tmp_path))
    env = tmp_path / ".ninja-mcp.env"
    env.write_text("# only comments here\nNINJA_ENABLE_DAEMON=true\n")
    dm = _make_manager(tmp_path)

    dm._save_enabled_modules(["coder"])

    text = env.read_text()
    assert "NINJA_ENABLED_MODULES=coder" in text
    assert "NINJA_ENABLE_DAEMON=true" in text


def test_save_roundtrip(tmp_path: Path, monkeypatch) -> None:
    """Repeated saves leave the last written value readable via ConfigManager."""
    monkeypatch.setenv("HOME", str(tmp_path))
    env = tmp_path / ".ninja-mcp.env"
    dm = _make_manager(tmp_path)

    dm._save_enabled_modules(["coder"])
    assert ConfigManager(str(env)).get("NINJA_ENABLED_MODULES") == "coder"

    dm._save_enabled_modules(["coder", "researcher"])
    assert ConfigManager(str(env)).get("NINJA_ENABLED_MODULES") == "coder,researcher"

    dm._save_enabled_modules(["coder"])
    assert ConfigManager(str(env)).get("NINJA_ENABLED_MODULES") == "coder"
