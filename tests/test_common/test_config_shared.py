"""
Unit tests for config_shared module.

Tests for API key definitions, IDE definitions, tool/IDE detection,
secret management, and utility functions.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

from ninja_config.config_shared import (
    API_KEYS,
    APIKeyDef,
    CODER_API_KEYS,
    DAEMON_CONFIG,
    IDES,
    IDEDef,
    RESEARCHER_API_KEYS,
    check_python,
    check_uv,
    detect_ides,
    detect_tools,
    get_secret,
    install_uv,
    mask_key,
    register_claude_mcp,
    save_secret,
)

if TYPE_CHECKING:
    pass


class TestAPIKeyDef:
    """Tests for APIKeyDef data class and API_KEYS collection."""

    def test_api_keys_count(self):
        assert len(API_KEYS) == 13

    def test_coder_api_keys_module(self):
        for k in CODER_API_KEYS:
            assert k.module == "coder"

    def test_researcher_api_keys_module(self):
        for k in RESEARCHER_API_KEYS:
            assert k.module == "researcher"

    def test_coder_and_researcher_cover_all(self):
        assert len(CODER_API_KEYS) + len(RESEARCHER_API_KEYS) == len(API_KEYS)

    def test_all_fields_non_empty(self):
        for k in API_KEYS:
            assert k.env_var, f"env_var empty for {k}"
            assert k.display_name, f"display_name empty for {k}"
            assert k.url, f"url empty for {k}"
            assert k.module, f"module empty for {k}"
            assert k.description, f"description empty for {k}"

    def test_no_duplicate_env_vars(self):
        env_vars = [k.env_var for k in API_KEYS]
        assert len(env_vars) == len(set(env_vars))

    def test_module_values_valid(self):
        for k in API_KEYS:
            assert k.module in ("coder", "researcher")

    def test_coder_api_keys_count(self):
        assert len(CODER_API_KEYS) == 11

    def test_researcher_api_keys_count(self):
        assert len(RESEARCHER_API_KEYS) == 2

    def test_frozen_dataclass(self):
        k = API_KEYS[0]
        with pytest.raises(AttributeError):
            k.env_var = "CHANGED"


class TestIDEDef:
    """Tests for IDEDef data class and IDES collection."""

    def test_ides_minimum_count(self):
        assert len(IDES) >= 3

    def test_ides_contains_expected(self):
        ids = {ide.id for ide in IDES}
        assert "claude" in ids
        assert "vscode" in ids
        assert "zed" in ids

    def test_all_fields_non_empty(self):
        for ide in IDES:
            assert ide.id, f"id empty for {ide}"
            assert ide.display_name, f"display_name empty for {ide}"
            assert ide.config_paths, f"config_paths empty for {ide}"

    def test_config_paths_are_paths(self):
        for ide in IDES:
            for p in ide.config_paths:
                assert isinstance(p, Path)

    def test_frozen_dataclass(self):
        ide = IDES[0]
        with pytest.raises(AttributeError):
            ide.id = "CHANGED"

    def test_no_duplicate_ids(self):
        ids = [ide.id for ide in IDES]
        assert len(ids) == len(set(ids))


class TestDaemonConfig:
    """Tests for DAEMON_CONFIG constant."""

    def test_has_ninja_enable_daemon(self):
        assert DAEMON_CONFIG["NINJA_ENABLE_DAEMON"] == "true"

    def test_has_port_keys(self):
        for module in ("CODER", "RESEARCHER", "SECRETARY", "RESOURCES", "PROMPTS"):
            key = f"NINJA_{module}_PORT"
            assert key in DAEMON_CONFIG, f"Missing {key}"

    def test_port_values_in_range(self):
        for key, value in DAEMON_CONFIG.items():
            if key.endswith("_PORT"):
                port = int(value)
                assert 1024 <= port <= 65535, f"{key}={port} out of range"


class TestMaskKey:
    """Tests for mask_key function."""

    def test_empty_string(self):
        assert mask_key("") == "*** NOT SET ***"

    def test_short_string(self):
        assert mask_key("abc") == "***"

    def test_exactly_eight_chars(self):
        assert mask_key("12345678") == "1234...5678"

    def test_seven_chars(self):
        assert mask_key("1234567") == "***"

    def test_long_key(self):
        assert mask_key("sk-or-1234567890") == "sk-o...7890"

    def test_nine_chars(self):
        assert mask_key("123456789") == "1234...6789"


class TestDetectTools:
    """Tests for detect_tools function."""

    @patch("ninja_config.config_shared.shutil.which")
    def test_returns_found_tools(self, mock_which):
        def side_effect(name):
            return {"/usr/bin/aider", "/usr/bin/claude"}.intersection(
                {f"/usr/bin/{name}"}
            ) or None

        mock_which.side_effect = lambda n: f"/usr/bin/{n}" if n in ("aider", "claude") else None

        result = detect_tools()

        assert "aider" in result
        assert "claude" in result
        assert result["aider"] == "/usr/bin/aider"
        assert result["claude"] == "/usr/bin/claude"
        assert "opencode" not in result
        assert "gemini" not in result
        assert "cursor" not in result

    @patch("ninja_config.config_shared.shutil.which", return_value=None)
    def test_no_tools_found(self, mock_which):
        result = detect_tools()
        assert result == {}

    @patch("ninja_config.config_shared.shutil.which")
    def test_all_tools_found(self, mock_which):
        mock_which.side_effect = lambda n: f"/usr/local/bin/{n}"
        result = detect_tools()
        assert len(result) == 5
        for name in ("aider", "opencode", "gemini", "claude", "cursor"):
            assert name in result


class TestDetectIdes:
    """Tests for detect_ides function."""

    @patch("ninja_config.config_shared.IDES", [
        IDEDef("test_ide", "Test IDE", (Path("/fake/path/config.json"),)),
    ])
    @patch.object(Path, "exists", return_value=True)
    def test_found_ide(self, mock_exists):
        result = detect_ides()
        assert "test_ide" in result
        assert result["test_ide"] == "/fake/path/config.json"

    @patch("ninja_config.config_shared.IDES", [
        IDEDef("test_ide", "Test IDE", (Path("/fake/path/config.json"),)),
    ])
    @patch.object(Path, "exists", return_value=False)
    def test_no_ide_found(self, mock_exists):
        result = detect_ides()
        assert result == {}

    @patch("ninja_config.config_shared.IDES", [
        IDEDef("multi", "Multi", (Path("/a"), Path("/b"))),
    ])
    def test_first_path_wins(self):
        with patch.object(Path, "exists", side_effect=[False, True]):
            result = detect_ides()
            assert "multi" in result
            assert result["multi"] == "/b"

    @patch("ninja_config.config_shared.IDES", [
        IDEDef("multi", "Multi", (Path("/a"), Path("/b"))),
    ])
    def test_stops_at_first_match(self):
        with patch.object(Path, "exists", side_effect=[True, False]):
            result = detect_ides()
            assert "multi" in result
            assert result["multi"] == "/a"


class TestCheckPython:
    """Tests for check_python function."""

    @patch("ninja_config.config_shared.sys")
    def test_python_311_true(self, mock_sys):
        mock_sys.version_info = (3, 11, 0)
        assert check_python() is True

    @patch("ninja_config.config_shared.sys")
    def test_python_310_false(self, mock_sys):
        mock_sys.version_info = (3, 10, 0)
        assert check_python() is False

    @patch("ninja_config.config_shared.sys")
    def test_python_312_true(self, mock_sys):
        mock_sys.version_info = (3, 12, 5)
        assert check_python() is True

    @patch("ninja_config.config_shared.sys")
    def test_python_39_false(self, mock_sys):
        mock_sys.version_info = (3, 9, 1)
        assert check_python() is False


class TestCheckUv:
    """Tests for check_uv function."""

    @patch("ninja_config.config_shared.shutil.which", return_value="/usr/bin/uv")
    def test_uv_found(self, mock_which):
        assert check_uv() is True

    @patch("ninja_config.config_shared.shutil.which", return_value=None)
    def test_uv_not_found(self, mock_which):
        assert check_uv() is False


class TestInstallUv:
    """Tests for install_uv function."""

    @patch("ninja_config.config_shared.subprocess.run")
    @patch("ninja_config.config_shared.Path.home", return_value=Path("/home/test"))
    @patch("os.environ", {"PATH": "/usr/bin"})
    def test_success(self, mock_home, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        result = install_uv()
        assert result is True
        mock_run.assert_called_once()

    @patch("ninja_config.config_shared.subprocess.run")
    def test_failure(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1)
        result = install_uv()
        assert result is False


class TestSaveSecret:
    """Tests for save_secret function."""

    def test_stores_via_secret_store(self):
        mock_store = MagicMock()
        mock_default_store = MagicMock(return_value=mock_store)
        mock_secrets_module = MagicMock(
            default_store=mock_default_store,
            SecretStoreUnavailable=type("SecretStoreUnavailable", (Exception,), {}),
        )

        with patch.dict(sys.modules, {"ninja_config.secrets_store": mock_secrets_module}):
            save_secret("TEST_KEY", "test_value")

        mock_store.set.assert_called_once_with("TEST_KEY", "test_value")

    def test_fallback_to_config_manager(self):
        mock_cm = MagicMock()
        mock_secrets_module = MagicMock(
            default_store=MagicMock(side_effect=Exception),
            SecretStoreUnavailable=type("SecretStoreUnavailable", (Exception,), {}),
        )

        with patch.dict(sys.modules, {"ninja_config.secrets_store": mock_secrets_module}):
            with patch("ninja_common.config_manager.ConfigManager", return_value=mock_cm):
                save_secret("TEST_KEY", "test_value")

        mock_cm.set.assert_called_once_with("TEST_KEY", "test_value")

    def test_empty_value_noop(self):
        with patch.dict(sys.modules, {"ninja_config.secrets_store": MagicMock()}):
            with patch("ninja_common.config_manager.ConfigManager") as mock_cm:
                save_secret("TEST_KEY", "")
                mock_cm.assert_not_called()


class TestGetSecret:
    """Tests for get_secret function."""

    def test_secret_store_returns_value(self):
        mock_store = MagicMock()
        mock_store.get.return_value = "stored_value"
        mock_secrets_module = MagicMock(default_store=MagicMock(return_value=mock_store))

        with patch.dict(sys.modules, {"ninja_config.secrets_store": mock_secrets_module}):
            result = get_secret("TEST_KEY")

        assert result == "stored_value"

    def test_falls_back_to_env(self):
        mock_store = MagicMock()
        mock_store.get.return_value = None
        mock_secrets_module = MagicMock(default_store=MagicMock(return_value=mock_store))

        with patch.dict(sys.modules, {"ninja_config.secrets_store": mock_secrets_module}):
            with patch("os.environ", {"TEST_KEY": "env_value"}):
                result = get_secret("TEST_KEY")

        assert result == "env_value"

    def test_falls_back_to_config_manager(self):
        mock_store = MagicMock()
        mock_store.get.return_value = None
        mock_secrets_module = MagicMock(default_store=MagicMock(return_value=mock_store))
        mock_cm = MagicMock()
        mock_cm.get.return_value = "config_value"

        with patch.dict(sys.modules, {"ninja_config.secrets_store": mock_secrets_module}):
            with patch("os.environ", {}):
                with patch("ninja_common.config_manager.ConfigManager", return_value=mock_cm):
                    result = get_secret("TEST_KEY")

        assert result == "config_value"

    def test_all_return_none(self):
        mock_store = MagicMock()
        mock_store.get.return_value = None
        mock_secrets_module = MagicMock(default_store=MagicMock(return_value=mock_store))
        mock_cm = MagicMock()
        mock_cm.get.return_value = None

        with patch.dict(sys.modules, {"ninja_config.secrets_store": mock_secrets_module}):
            with patch("os.environ", {}):
                with patch("ninja_common.config_manager.ConfigManager", return_value=mock_cm):
                    result = get_secret("TEST_KEY")

        assert result is None

    def test_secret_store_exception_falls_back(self):
        mock_cm = MagicMock()
        mock_cm.get.return_value = "fallback_value"
        mock_secrets_module = MagicMock(
            default_store=MagicMock(side_effect=RuntimeError("no store")),
        )

        with patch.dict(sys.modules, {"ninja_config.secrets_store": mock_secrets_module}):
            with patch("os.environ", {}):
                with patch("ninja_common.config_manager.ConfigManager", return_value=mock_cm):
                    result = get_secret("TEST_KEY")

        assert result == "fallback_value"


class TestRegisterClaudeMcp:
    """Tests for register_claude_mcp function."""

    @patch("ninja_config.config_shared.shutil.which", return_value=None)
    def test_claude_not_found(self, mock_which):
        result = register_claude_mcp()
        assert result == 0

    @patch("ninja_config.config_shared.subprocess.run")
    @patch("ninja_config.config_shared.shutil.which", return_value="/usr/bin/claude")
    def test_registers_all_servers(self, mock_which, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        result = register_claude_mcp()
        assert result == 3
        assert mock_run.call_count == 6  # 3 remove + 3 add

    @patch("ninja_config.config_shared.subprocess.run")
    @patch("ninja_config.config_shared.shutil.which", return_value="/usr/bin/claude")
    def test_partial_failure(self, mock_which, mock_run):
        mock_run.side_effect = [
            MagicMock(returncode=0),  # remove ninja-coder
            MagicMock(returncode=0),  # add ninja-coder → count=1
            MagicMock(returncode=0),  # remove ninja-researcher
            MagicMock(returncode=1),  # add ninja-researcher → fail
            MagicMock(returncode=0),  # remove ninja-secretary
            MagicMock(returncode=0),  # add ninja-secretary → count=2
        ]
        result = register_claude_mcp()
        assert result == 2
