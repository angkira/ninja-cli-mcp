"""
Unit tests for ConfigManager.

Tests for configuration file reading, writing, and management.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from ninja_common.config_manager import ConfigManager


class TestConfigManager:
    """Tests for ConfigManager."""

    def test_read_empty_config(self):
        """Test reading non-existent config file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / ".ninja-mcp.env"
            manager = ConfigManager(str(config_file))

            config = manager.read_config()

            assert config == {}

    def test_write_and_read_config(self):
        """Test writing and reading configuration."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / ".ninja-mcp.env"
            manager = ConfigManager(str(config_file))

            # Write config
            config_data = {
                "OPENROUTER_API_KEY": "test_key_123",
                "NINJA_CODER_MODEL": "test/model",
            }
            manager.write_config(config_data)

            # Read back
            read_config = manager.read_config()

            assert read_config == config_data

    def test_get_existing_key(self):
        """Test getting an existing config value."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / ".ninja-mcp.env"
            manager = ConfigManager(str(config_file))

            manager.write_config({"TEST_KEY": "test_value"})

            value = manager.get("TEST_KEY")

            assert value == "test_value"

    def test_get_nonexistent_key(self):
        """Test getting a non-existent config value."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / ".ninja-mcp.env"
            manager = ConfigManager(str(config_file))

            value = manager.get("NONEXISTENT_KEY")

            assert value is None

    def test_get_with_default(self):
        """Test getting with default value."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / ".ninja-mcp.env"
            manager = ConfigManager(str(config_file))

            value = manager.get("NONEXISTENT_KEY", default="default_value")

            assert value == "default_value"

    def test_set_new_key(self):
        """Test setting a new config value."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / ".ninja-mcp.env"
            manager = ConfigManager(str(config_file))

            manager.set("NEW_KEY", "new_value")

            value = manager.get("NEW_KEY")

            assert value == "new_value"

    def test_set_updates_existing_key(self):
        """Test that set updates existing key."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / ".ninja-mcp.env"
            manager = ConfigManager(str(config_file))

            manager.set("KEY", "old_value")
            manager.set("KEY", "new_value")

            value = manager.get("KEY")

            assert value == "new_value"

    def test_update_multiple_values(self):
        """Test updating multiple config values at once."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / ".ninja-mcp.env"
            manager = ConfigManager(str(config_file))

            manager.set("KEY1", "value1")

            updates = {"KEY1": "updated1", "KEY2": "value2", "KEY3": "value3"}
            manager.update(updates)

            config = manager.read_config()

            assert config["KEY1"] == "updated1"
            assert config["KEY2"] == "value2"
            assert config["KEY3"] == "value3"

    def test_delete_key(self):
        """Test deleting a config key."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / ".ninja-mcp.env"
            manager = ConfigManager(str(config_file))

            manager.set("KEY_TO_DELETE", "value")
            manager.delete("KEY_TO_DELETE")

            value = manager.get("KEY_TO_DELETE")

            assert value is None

    def test_list_all(self):
        """Test listing all configuration."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / ".ninja-mcp.env"
            manager = ConfigManager(str(config_file))

            test_config = {
                "KEY1": "value1",
                "KEY2": "value2",
                "KEY3": "value3",
            }
            manager.write_config(test_config)

            all_config = manager.list_all()

            assert all_config == test_config

    def test_get_masked_api_key(self):
        """Test that API keys are masked properly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / ".ninja-mcp.env"
            manager = ConfigManager(str(config_file))

            manager.set("OPENROUTER_API_KEY", "sk-1234567890abcdefghijklmnop")

            masked = manager.get_masked("OPENROUTER_API_KEY")

            assert masked == "sk-12345...mnop"
            assert "67890abc" not in masked

    def test_get_masked_short_key(self):
        """Test masking short API keys."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / ".ninja-mcp.env"
            manager = ConfigManager(str(config_file))

            manager.set("SHORT_KEY", "short")

            masked = manager.get_masked("SHORT_KEY")

            # Short values (<=12 chars) should not be masked
            assert masked == "short"

    def test_get_masked_non_key_value(self):
        """Test that non-API-key values are not masked."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / ".ninja-mcp.env"
            manager = ConfigManager(str(config_file))

            manager.set("NINJA_CODER_MODEL", "anthropic/claude-sonnet-4")

            masked = manager.get_masked("NINJA_CODER_MODEL")

            # Non-key values should not be masked
            assert masked == "anthropic/claude-sonnet-4"

    def test_config_file_permissions(self):
        """Test that config file has correct permissions (600)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / ".ninja-mcp.env"
            manager = ConfigManager(str(config_file))

            manager.write_config({"KEY": "value"})

            # Check file permissions
            import stat

            file_stat = config_file.stat()
            stat.filemode(file_stat.st_mode)

            # Should be readable and writable by owner only
            assert file_stat.st_mode & stat.S_IRUSR
            assert file_stat.st_mode & stat.S_IWUSR
            assert not (file_stat.st_mode & stat.S_IRGRP)
            assert not (file_stat.st_mode & stat.S_IROTH)

    def test_preserve_comments(self):
        """Test that comments are preserved when updating config."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / ".ninja-mcp.env"

            # Create initial config with comments
            config_file.write_text(
                """# Ninja MCP Configuration
# Generated test

# API Keys
export OPENROUTER_API_KEY='old_key'

# Models
export NINJA_CODER_MODEL='old_model'
"""
            )

            manager = ConfigManager(str(config_file))

            # Update a value
            manager.set("OPENROUTER_API_KEY", "new_key")

            # Read file content
            content = config_file.read_text()

            # Comments should be preserved
            assert "# Ninja MCP Configuration" in content
            assert "# API Keys" in content
            # Value should be updated
            assert "new_key" in content
            assert "old_key" not in content

    def test_handle_quotes_in_values(self):
        """Test handling of different quote styles."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / ".ninja-mcp.env"
            manager = ConfigManager(str(config_file))

            # Set value with single quotes
            manager.set("KEY1", "value with spaces")

            # Read back
            value = manager.get("KEY1")

            assert value == "value with spaces"
