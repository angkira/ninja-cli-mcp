"""Tests for init target modules (specifically Junie)."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any


if TYPE_CHECKING:
    import pytest


def _make_args(**kwargs: Any) -> SimpleNamespace:
    defaults = {"dry_run": False, "force": False, "direct": False}
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


class TestJunieTarget:
    """Unit tests for the junie target module."""

    def test_detect_true_when_dir_exists(self, tmp_path: Path) -> None:
        """detect() returns True when detect_dir (~/.junie) exists."""
        from ninja_common.init_targets import junie

        orig_detect = junie.detect_dir
        try:
            fake_dir = tmp_path / ".junie"
            fake_dir.mkdir(parents=True, exist_ok=True)
            junie.detect_dir = fake_dir

            assert junie.detect() is True
        finally:
            junie.detect_dir = orig_detect

    def test_detect_false_when_dir_missing(self, tmp_path: Path) -> None:
        """detect() returns False when detect_dir does not exist."""
        from ninja_common.init_targets import junie

        orig_detect = junie.detect_dir
        try:
            fake_dir = tmp_path / "nonexistent_junie_dir"
            junie.detect_dir = fake_dir

            assert junie.detect() is False
        finally:
            junie.detect_dir = orig_detect

    def test_install_fresh(self, tmp_path: Path) -> None:
        """install() creates ~/.junie/mcp/ subdirectory and mcp.json with all 4 servers."""
        from ninja_common.init_targets import junie

        orig_dir = junie.config_dir
        orig_file = junie.config_file
        try:
            target_dir = tmp_path / ".junie" / "mcp"
            target_file = target_dir / "mcp.json"
            junie.config_dir = target_dir
            junie.config_file = target_file

            rc = junie.install(_make_args())
            assert rc == 0
            assert target_dir.is_dir()
            assert target_file.is_file()

            data = json.loads(target_file.read_text(encoding="utf-8"))
            servers = data.get("mcpServers", {})
            assert "ninja-coder" in servers
            assert "ninja-researcher" in servers
            assert "ninja-secretary" in servers
            assert "ninja-agent" in servers
        finally:
            junie.config_dir = orig_dir
            junie.config_file = orig_file

    def test_install_dry_run_no_write(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """install(--dry-run) prints what would be written without creating files."""
        from ninja_common.init_targets import junie

        orig_dir = junie.config_dir
        orig_file = junie.config_file
        try:
            target_dir = tmp_path / ".junie" / "mcp"
            target_file = target_dir / "mcp.json"
            junie.config_dir = target_dir
            junie.config_file = target_file

            rc = junie.install(_make_args(dry_run=True))
            assert rc == 0
            assert not target_file.exists()
            assert not target_dir.exists()

            captured = capsys.readouterr().out
            assert "Dry run" in captured
            assert "ninja-coder" in captured
        finally:
            junie.config_dir = orig_dir
            junie.config_file = orig_file

    def test_install_merges_existing_servers(self, tmp_path: Path) -> None:
        """install() preserves existing non-ninja servers when merging."""
        from ninja_common.init_targets import junie

        orig_dir = junie.config_dir
        orig_file = junie.config_file
        try:
            target_dir = tmp_path / ".junie" / "mcp"
            target_dir.mkdir(parents=True, exist_ok=True)
            target_file = target_dir / "mcp.json"

            existing: dict[str, Any] = {
                "mcpServers": {
                    "custom-tool": {
                        "command": "custom-cmd",
                        "args": ["--port", "8080"],
                    }
                }
            }
            target_file.write_text(json.dumps(existing, indent=2), encoding="utf-8")

            junie.config_dir = target_dir
            junie.config_file = target_file

            rc = junie.install(_make_args())
            assert rc == 0

            data = json.loads(target_file.read_text(encoding="utf-8"))
            servers = data["mcpServers"]
            assert "custom-tool" in servers
            assert servers["custom-tool"]["command"] == "custom-cmd"
            assert "ninja-coder" in servers
            assert "ninja-researcher" in servers
            assert "ninja-secretary" in servers
            assert "ninja-agent" in servers
        finally:
            junie.config_dir = orig_dir
            junie.config_file = orig_file

    def test_install_conflict_without_force_fails(self, tmp_path: Path) -> None:
        """install() returns non-zero when a server already exists and --force is not passed."""
        from ninja_common.init_targets import junie

        orig_dir = junie.config_dir
        orig_file = junie.config_file
        try:
            target_dir = tmp_path / ".junie" / "mcp"
            target_dir.mkdir(parents=True, exist_ok=True)
            target_file = target_dir / "mcp.json"

            existing: dict[str, Any] = {
                "mcpServers": {
                    "ninja-coder": {
                        "command": "old-coder",
                        "args": [],
                    }
                }
            }
            target_file.write_text(json.dumps(existing, indent=2), encoding="utf-8")

            junie.config_dir = target_dir
            junie.config_file = target_file

            rc = junie.install(_make_args(force=False))
            assert rc != 0

            # Content not overwritten
            data = json.loads(target_file.read_text(encoding="utf-8"))
            assert data["mcpServers"]["ninja-coder"]["command"] == "old-coder"
        finally:
            junie.config_dir = orig_dir
            junie.config_file = orig_file

    def test_install_conflict_with_force_overwrites(self, tmp_path: Path) -> None:
        """install(--force) overwrites existing ninja servers."""
        from ninja_common.init_targets import junie

        orig_dir = junie.config_dir
        orig_file = junie.config_file
        try:
            target_dir = tmp_path / ".junie" / "mcp"
            target_dir.mkdir(parents=True, exist_ok=True)
            target_file = target_dir / "mcp.json"

            existing: dict[str, Any] = {
                "mcpServers": {
                    "ninja-coder": {
                        "command": "old-coder",
                        "args": [],
                    }
                }
            }
            target_file.write_text(json.dumps(existing, indent=2), encoding="utf-8")

            junie.config_dir = target_dir
            junie.config_file = target_file

            rc = junie.install(_make_args(force=True))
            assert rc == 0

            data = json.loads(target_file.read_text(encoding="utf-8"))
            assert data["mcpServers"]["ninja-coder"]["command"] == "ninja-mcp"
            assert data["mcpServers"]["ninja-coder"]["args"] == ["daemon", "connect", "coder"]
        finally:
            junie.config_dir = orig_dir
            junie.config_file = orig_file

    def test_install_backup_created(self, tmp_path: Path) -> None:
        """install() creates .pre-ninja.bak on first modification."""
        from ninja_common.init_targets import junie

        orig_dir = junie.config_dir
        orig_file = junie.config_file
        try:
            target_dir = tmp_path / ".junie" / "mcp"
            target_dir.mkdir(parents=True, exist_ok=True)
            target_file = target_dir / "mcp.json"
            target_file.write_text('{"mcpServers": {}}', encoding="utf-8")

            junie.config_dir = target_dir
            junie.config_file = target_file

            rc = junie.install(_make_args())
            assert rc == 0

            bak = Path(str(target_file) + ".pre-ninja.bak")
            assert bak.is_file()
            first_mtime = bak.stat().st_mtime

            # Second write does not overwrite backup
            junie.install(_make_args(force=True))
            assert bak.stat().st_mtime == first_mtime
        finally:
            junie.config_dir = orig_dir
            junie.config_file = orig_file
