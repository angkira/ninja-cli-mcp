"""Tests for ninja-mcp init CLI (Phase 3)."""

from __future__ import annotations

import json
import textwrap
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_args(**kwargs: Any) -> SimpleNamespace:
    """Build a minimal argparse-like namespace for install() calls."""
    defaults = {"dry_run": False, "force": False, "direct": False}
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


# ---------------------------------------------------------------------------
# generic
# ---------------------------------------------------------------------------


class TestGeneric:
    def test_prints_mcp_json(self, capsys: pytest.CaptureFixture[str]) -> None:
        """generic.install prints dist/mcp.json with a header comment."""
        from ninja_common.init_targets import generic

        rc = generic.install(_make_args())
        assert rc == 0
        captured = capsys.readouterr().out
        assert "mcpServers" in captured
        assert "ninja-coder" in captured
        # Header comment present
        assert "generic MCP" in captured or "Paste" in captured

    def test_output_is_valid_json(self, capsys: pytest.CaptureFixture[str]) -> None:
        """The JSON portion of generic output is parseable."""
        from ninja_common.init_targets import generic

        generic.install(_make_args())
        out = capsys.readouterr().out
        # Extract only lines that look like JSON (after the comment block)
        json_lines = [
            line for line in out.splitlines() if not line.startswith("#") and line.strip()
        ]
        json_text = "\n".join(json_lines)
        data = json.loads(json_text)
        assert "mcpServers" in data
        assert "ninja-coder" in data["mcpServers"]

    def test_content_matches_dist_file(self, capsys: pytest.CaptureFixture[str]) -> None:
        """generic output reproduces the exact dist/mcp.json content."""
        from ninja_common.init_targets import generic
        from ninja_common.init_targets._common import load_mcp_json

        generic.install(_make_args())
        out = capsys.readouterr().out
        expected = json.dumps(load_mcp_json(), indent=2)
        assert expected in out


# ---------------------------------------------------------------------------
# claude-code
# ---------------------------------------------------------------------------


class TestClaudeCode:
    def test_plugin_mode_default(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Without --direct, prints plugin-mode instructions."""
        from ninja_common.init_targets import claude_code

        rc = claude_code.install(_make_args(direct=False))
        assert rc == 0
        out = capsys.readouterr().out
        assert "/plugin install" in out
        assert "ninja@" in out

    def test_dry_run_no_write(self, tmp_path: Path) -> None:
        """--direct --dry-run prints diff but does not write."""
        from ninja_common.init_targets import claude_code

        # Patch the global path constants to use tmp_path
        orig_dir = claude_code._CLAUDE_DIR
        orig_file = claude_code._SETTINGS_FILE
        try:
            claude_code._CLAUDE_DIR = tmp_path / ".claude"
            claude_code._SETTINGS_FILE = tmp_path / ".claude" / "settings.json"

            rc = claude_code.install(_make_args(direct=True, dry_run=True))
            assert rc == 0
            assert not (tmp_path / ".claude" / "settings.json").exists()
        finally:
            claude_code._CLAUDE_DIR = orig_dir
            claude_code._SETTINGS_FILE = orig_file

    def test_direct_fresh_install(self, tmp_path: Path) -> None:
        """--direct writes settings.json when none exists."""
        from ninja_common.init_targets import claude_code

        orig_dir = claude_code._CLAUDE_DIR
        orig_file = claude_code._SETTINGS_FILE
        try:
            target_dir = tmp_path / ".claude"
            target_file = target_dir / "settings.json"
            claude_code._CLAUDE_DIR = target_dir
            claude_code._SETTINGS_FILE = target_file

            rc = claude_code.install(_make_args(direct=True))
            assert rc == 0
            assert target_file.exists()
            data = json.loads(target_file.read_text())
            assert "ninja-coder" in data["mcpServers"]
        finally:
            claude_code._CLAUDE_DIR = orig_dir
            claude_code._SETTINGS_FILE = orig_file

    def test_direct_merges_existing_servers(self, tmp_path: Path) -> None:
        """--direct preserves existing servers that are not ninja's."""
        from ninja_common.init_targets import claude_code

        orig_dir = claude_code._CLAUDE_DIR
        orig_file = claude_code._SETTINGS_FILE
        try:
            target_dir = tmp_path / ".claude"
            target_dir.mkdir()
            target_file = target_dir / "settings.json"
            existing: dict[str, Any] = {
                "mcpServers": {"my-custom-server": {"command": "custom", "args": [], "env": {}}}
            }
            target_file.write_text(json.dumps(existing, indent=2))

            claude_code._CLAUDE_DIR = target_dir
            claude_code._SETTINGS_FILE = target_file

            rc = claude_code.install(_make_args(direct=True))
            assert rc == 0
            data = json.loads(target_file.read_text())
            assert "my-custom-server" in data["mcpServers"]
            assert "ninja-coder" in data["mcpServers"]
        finally:
            claude_code._CLAUDE_DIR = orig_dir
            claude_code._SETTINGS_FILE = orig_file

    def test_direct_conflict_no_force_exits_nonzero(self, tmp_path: Path) -> None:
        """Conflict without --force returns non-zero exit code."""
        from ninja_common.init_targets import claude_code

        orig_dir = claude_code._CLAUDE_DIR
        orig_file = claude_code._SETTINGS_FILE
        try:
            target_dir = tmp_path / ".claude"
            target_dir.mkdir()
            target_file = target_dir / "settings.json"
            existing = {
                "mcpServers": {"ninja-coder": {"command": "ninja-coder", "args": [], "env": {}}}
            }
            target_file.write_text(json.dumps(existing, indent=2))

            claude_code._CLAUDE_DIR = target_dir
            claude_code._SETTINGS_FILE = target_file

            rc = claude_code.install(_make_args(direct=True, force=False))
            assert rc != 0
        finally:
            claude_code._CLAUDE_DIR = orig_dir
            claude_code._SETTINGS_FILE = orig_file

    def test_direct_conflict_with_force_overwrites(self, tmp_path: Path) -> None:
        """Conflict with --force overwrites existing server."""
        from ninja_common.init_targets import claude_code

        orig_dir = claude_code._CLAUDE_DIR
        orig_file = claude_code._SETTINGS_FILE
        try:
            target_dir = tmp_path / ".claude"
            target_dir.mkdir()
            target_file = target_dir / "settings.json"
            existing = {
                "mcpServers": {"ninja-coder": {"command": "OLD-COMMAND", "args": [], "env": {}}}
            }
            target_file.write_text(json.dumps(existing, indent=2))

            claude_code._CLAUDE_DIR = target_dir
            claude_code._SETTINGS_FILE = target_file

            rc = claude_code.install(_make_args(direct=True, force=True))
            assert rc == 0
            data = json.loads(target_file.read_text())
            assert data["mcpServers"]["ninja-coder"]["command"] == "ninja-daemon"
            assert data["mcpServers"]["ninja-coder"]["args"] == ["connect", "coder"]
        finally:
            claude_code._CLAUDE_DIR = orig_dir
            claude_code._SETTINGS_FILE = orig_file

    def test_backup_created_on_first_write(self, tmp_path: Path) -> None:
        """Backup .pre-ninja.bak is created before first modification."""
        from ninja_common.init_targets import claude_code

        orig_dir = claude_code._CLAUDE_DIR
        orig_file = claude_code._SETTINGS_FILE
        try:
            target_dir = tmp_path / ".claude"
            target_dir.mkdir()
            target_file = target_dir / "settings.json"
            target_file.write_text('{"mcpServers": {}}')

            claude_code._CLAUDE_DIR = target_dir
            claude_code._SETTINGS_FILE = target_file

            claude_code.install(_make_args(direct=True))
            bak = Path(str(target_file) + ".pre-ninja.bak")
            assert bak.exists()
        finally:
            claude_code._CLAUDE_DIR = orig_dir
            claude_code._SETTINGS_FILE = orig_file

    def test_backup_not_overwritten_on_second_write(self, tmp_path: Path) -> None:
        """Backup file is NOT overwritten on subsequent runs."""
        from ninja_common.init_targets import claude_code

        orig_dir = claude_code._CLAUDE_DIR
        orig_file = claude_code._SETTINGS_FILE
        try:
            target_dir = tmp_path / ".claude"
            target_dir.mkdir()
            target_file = target_dir / "settings.json"
            target_file.write_text('{"mcpServers": {}}')

            claude_code._CLAUDE_DIR = target_dir
            claude_code._SETTINGS_FILE = target_file

            claude_code.install(_make_args(direct=True))
            bak = Path(str(target_file) + ".pre-ninja.bak")
            first_mtime = bak.stat().st_mtime

            # Second run — backup must not be touched
            claude_code.install(_make_args(direct=True, force=True))
            assert bak.stat().st_mtime == first_mtime
        finally:
            claude_code._CLAUDE_DIR = orig_dir
            claude_code._SETTINGS_FILE = orig_file


# ---------------------------------------------------------------------------
# codex
# ---------------------------------------------------------------------------


class TestCodex:
    def test_fresh_install(self, tmp_path: Path) -> None:
        """Writes config.toml when none exists."""
        from ninja_common.init_targets import codex

        orig_dir = codex._CODEX_DIR
        orig_file = codex._CONFIG_FILE
        try:
            target_dir = tmp_path / ".codex"
            target_file = target_dir / "config.toml"
            codex._CODEX_DIR = target_dir
            codex._CONFIG_FILE = target_file

            rc = codex.install(_make_args())
            assert rc == 0
            assert target_file.exists()
            text = target_file.read_text()
            assert "ninja_coder" in text
        finally:
            codex._CODEX_DIR = orig_dir
            codex._CONFIG_FILE = orig_file

    def test_merges_preserving_comments(self, tmp_path: Path) -> None:
        """Existing TOML comments are preserved after merge."""
        import tomlkit

        from ninja_common.init_targets import codex

        orig_dir = codex._CODEX_DIR
        orig_file = codex._CONFIG_FILE
        try:
            target_dir = tmp_path / ".codex"
            target_dir.mkdir()
            target_file = target_dir / "config.toml"

            # Create TOML with a comment that must survive the merge
            existing_toml = textwrap.dedent("""\
                # my important comment
                [settings]
                theme = "dark"
            """)
            target_file.write_text(existing_toml)

            codex._CODEX_DIR = target_dir
            codex._CONFIG_FILE = target_file

            rc = codex.install(_make_args())
            assert rc == 0
            result = target_file.read_text()
            # Comment must be preserved
            assert "# my important comment" in result
            # Ninja sections added
            assert "ninja_coder" in result
            # Original setting preserved
            doc = tomlkit.parse(result)
            assert doc["settings"]["theme"] == "dark"  # type: ignore[index]
        finally:
            codex._CODEX_DIR = orig_dir
            codex._CONFIG_FILE = orig_file

    def test_conflict_no_force_exits_nonzero(self, tmp_path: Path) -> None:
        """Conflict without --force returns non-zero exit code."""
        from ninja_common.init_targets import codex

        orig_dir = codex._CODEX_DIR
        orig_file = codex._CONFIG_FILE
        try:
            target_dir = tmp_path / ".codex"
            target_dir.mkdir()
            target_file = target_dir / "config.toml"
            target_file.write_text("[mcp_servers.ninja_coder]\ncommand = 'OLD'\nargs = []\n")

            codex._CODEX_DIR = target_dir
            codex._CONFIG_FILE = target_file

            rc = codex.install(_make_args(force=False))
            assert rc != 0
        finally:
            codex._CODEX_DIR = orig_dir
            codex._CONFIG_FILE = orig_file

    def test_dry_run_no_write(self, tmp_path: Path) -> None:
        """--dry-run prints diff but does not write."""
        from ninja_common.init_targets import codex

        orig_dir = codex._CODEX_DIR
        orig_file = codex._CONFIG_FILE
        try:
            target_dir = tmp_path / ".codex"
            target_file = target_dir / "config.toml"
            codex._CODEX_DIR = target_dir
            codex._CONFIG_FILE = target_file

            rc = codex.install(_make_args(dry_run=True))
            assert rc == 0
            assert not target_file.exists()
        finally:
            codex._CODEX_DIR = orig_dir
            codex._CONFIG_FILE = orig_file

    def test_backup_created_and_not_overwritten(self, tmp_path: Path) -> None:
        """Backup is created on first write and untouched on second."""
        from ninja_common.init_targets import codex

        orig_dir = codex._CODEX_DIR
        orig_file = codex._CONFIG_FILE
        try:
            target_dir = tmp_path / ".codex"
            target_dir.mkdir()
            target_file = target_dir / "config.toml"
            target_file.write_text("# existing config\n")

            codex._CODEX_DIR = target_dir
            codex._CONFIG_FILE = target_file

            codex.install(_make_args())
            bak = Path(str(target_file) + ".pre-ninja.bak")
            assert bak.exists()
            first_mtime = bak.stat().st_mtime

            codex.install(_make_args(force=True))
            assert bak.stat().st_mtime == first_mtime
        finally:
            codex._CODEX_DIR = orig_dir
            codex._CONFIG_FILE = orig_file


# ---------------------------------------------------------------------------
# cursor
# ---------------------------------------------------------------------------


class TestCursor:
    def test_fresh_install(self, tmp_path: Path) -> None:
        """Writes mcp.json when ~/.cursor/ does not yet exist."""
        from ninja_common.init_targets import cursor

        orig_dir = cursor._CURSOR_DIR
        orig_file = cursor._MCP_FILE
        try:
            target_dir = tmp_path / ".cursor"
            target_file = target_dir / "mcp.json"
            cursor._CURSOR_DIR = target_dir
            cursor._MCP_FILE = target_file

            rc = cursor.install(_make_args())
            assert rc == 0
            assert target_file.exists()
            data = json.loads(target_file.read_text())
            assert "ninja-coder" in data["mcpServers"]
        finally:
            cursor._CURSOR_DIR = orig_dir
            cursor._MCP_FILE = orig_file

    def test_dry_run_no_write(self, tmp_path: Path) -> None:
        """--dry-run does not create the file."""
        from ninja_common.init_targets import cursor

        orig_dir = cursor._CURSOR_DIR
        orig_file = cursor._MCP_FILE
        try:
            target_dir = tmp_path / ".cursor"
            target_file = target_dir / "mcp.json"
            cursor._CURSOR_DIR = target_dir
            cursor._MCP_FILE = target_file

            rc = cursor.install(_make_args(dry_run=True))
            assert rc == 0
            assert not target_file.exists()
        finally:
            cursor._CURSOR_DIR = orig_dir
            cursor._MCP_FILE = orig_file


# ---------------------------------------------------------------------------
# detect
# ---------------------------------------------------------------------------


class TestDetect:
    def test_detect_returns_correct_hosts(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """detect shows claude-code and cursor as detected when their dirs exist."""
        from ninja_common.init_targets import claude_code, cursor

        orig_cc = claude_code._CLAUDE_DIR
        orig_cu = cursor._CURSOR_DIR
        try:
            fake_claude = tmp_path / ".claude"
            fake_claude.mkdir()
            fake_cursor = tmp_path / ".cursor"
            fake_cursor.mkdir()

            claude_code._CLAUDE_DIR = fake_claude
            cursor._CURSOR_DIR = fake_cursor

            from ninja_common import init_cli

            args = SimpleNamespace(func=init_cli._cmd_detect)
            rc = init_cli._cmd_detect(args)
            assert rc == 0

            out = capsys.readouterr().out
            # claude-code and cursor show as detected
            assert "detected" in out
        finally:
            claude_code._CLAUDE_DIR = orig_cc
            cursor._CURSOR_DIR = orig_cu


# ---------------------------------------------------------------------------
# CLI integration (argparse level)
# ---------------------------------------------------------------------------


class TestCLI:
    def test_help_exits_zero(self) -> None:
        """ninja-mcp init --help exits 0."""
        from ninja_common.init_cli import _build_parser

        parser = _build_parser()
        with pytest.raises(SystemExit) as exc_info:
            parser.parse_args(["init", "--help"])
        assert exc_info.value.code == 0

    def test_generic_via_main(self, capsys: pytest.CaptureFixture[str]) -> None:
        """main() dispatches init generic correctly."""
        import sys

        from ninja_common.init_cli import main

        sys.argv = ["ninja-mcp", "init", "generic"]
        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 0
        out = capsys.readouterr().out
        assert "mcpServers" in out

    def test_detect_via_main(self, capsys: pytest.CaptureFixture[str]) -> None:
        """main() dispatches init detect without error."""
        import sys

        from ninja_common.init_cli import main

        sys.argv = ["ninja-mcp", "init", "detect"]
        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 0

    def test_claude_code_dry_run_no_direct(self, capsys: pytest.CaptureFixture[str]) -> None:
        """ninja-mcp init claude-code --dry-run (no --direct) prints plugin instructions."""
        import sys

        from ninja_common.init_cli import main

        sys.argv = ["ninja-mcp", "init", "claude-code", "--dry-run"]
        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 0
        out = capsys.readouterr().out
        assert "/plugin install" in out

    def test_no_subcommand_prints_help(self, capsys: pytest.CaptureFixture[str]) -> None:
        """ninja-mcp with no args prints help and exits 0."""
        import sys

        from ninja_common.init_cli import main

        sys.argv = ["ninja-mcp"]
        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 0
