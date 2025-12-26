"""
Configuration manager for ninja-mcp modules.

Provides functionality to view and update configuration settings
stored in ~/.ninja-mcp.env file.
"""

from __future__ import annotations

import os
import re
from pathlib import Path


class ConfigManager:
    """Manages ninja-mcp configuration stored in ~/.ninja-mcp.env."""

    def __init__(self, config_file: str | None = None):
        """
        Initialize the config manager.

        Args:
            config_file: Path to config file. Defaults to ~/.ninja-mcp.env.
        """
        if config_file:
            self.config_file = Path(config_file)
        else:
            self.config_file = Path.home() / ".ninja-mcp.env"

    def read_config(self) -> dict[str, str]:
        """
        Read configuration from file.

        Returns:
            Dictionary of environment variables.
        """
        config = {}

        if not self.config_file.exists():
            return config

        with self.config_file.open() as f:
            for raw_line in f:
                line = raw_line.strip()

                # Skip comments and empty lines
                if not line or line.startswith("#"):
                    continue

                # Parse export statements
                match = re.match(r"export\s+(\w+)=['\"]?(.*?)['\"]?$", line)
                if match:
                    key, value = match.groups()
                    config[key] = value

        return config

    def write_config(self, config: dict[str, str]) -> None:
        """
        Write configuration to file.

        Args:
            config: Dictionary of environment variables to write.
        """
        # Read existing file to preserve structure
        lines = []

        if self.config_file.exists():
            with self.config_file.open() as f:
                for line in f:
                    stripped = line.strip()

                    # Track sections
                    if stripped.startswith("# ===="):
                        # Extract section name
                        lines.index(line) + 1 if line in lines else len(lines)
                        lines.append(line)
                        continue

                    if stripped.startswith("#") and not stripped.startswith("# ===="):
                        # Check if this is a section header
                        if "Module" in stripped or "Configuration" in stripped:
                            pass
                        lines.append(line)
                        continue

                    # Update export statements
                    match = re.match(r"export\s+(\w+)=", stripped)
                    if match:
                        key = match.group(1)
                        if key in config:
                            # Update the value
                            lines.append(f"export {key}='{config[key]}'\n")
                            # Remove from config dict (already processed)
                            del config[key]
                        # else: skip this line (key was deleted or not in config)
                    else:
                        lines.append(line)
        else:
            # Create new config file
            lines.append("# Ninja MCP Configuration\n")
            lines.append(f"# Generated on {__import__('datetime').datetime.now()}\n")
            lines.append("\n")
            lines.append("# ============================================================================\n")
            lines.append("# Common Configuration\n")
            lines.append("# ============================================================================\n")
            lines.append("\n")

        # Add any remaining config items (new variables)
        if config:
            lines.append("\n")
            for key, value in config.items():
                lines.append(f"export {key}='{value}'\n")

        # Write to file
        self.config_file.parent.mkdir(parents=True, exist_ok=True)
        with self.config_file.open("w") as f:
            f.writelines(lines)

        # Set permissions to 600 (read/write for owner only)
        self.config_file.chmod(0o600)

    def get(self, key: str, default: str | None = None) -> str | None:
        """
        Get a configuration value.

        Args:
            key: Configuration key.
            default: Default value if key not found.

        Returns:
            Configuration value or default.
        """
        config = self.read_config()
        return config.get(key, default)

    def set(self, key: str, value: str) -> None:
        """
        Set a configuration value.

        Args:
            key: Configuration key.
            value: Configuration value.
        """
        config = self.read_config()
        config[key] = value
        self.write_config(config)

    def update(self, updates: dict[str, str]) -> None:
        """
        Update multiple configuration values.

        Args:
            updates: Dictionary of key-value pairs to update.
        """
        config = self.read_config()
        config.update(updates)
        self.write_config(config)

    def list_all(self) -> dict[str, str]:
        """
        List all configuration values.

        Returns:
            Dictionary of all configuration values.
        """
        return self.read_config()

    def delete(self, key: str) -> None:
        """
        Delete a configuration value.

        Args:
            key: Configuration key to delete.
        """
        config = self.read_config()
        if key in config:
            del config[key]
            self.write_config(config)

    def export_env(self) -> None:
        """
        Export all configuration values to environment variables.
        """
        config = self.read_config()
        for key, value in config.items():
            os.environ[key] = value

    def get_masked(self, key: str) -> str | None:
        """
        Get a configuration value with masking for API keys.

        Args:
            key: Configuration key.

        Returns:
            Masked configuration value or None.
        """
        value = self.get(key)
        if not value:
            return None

        # Mask API keys (show first 8 and last 4 chars)
        if ("API_KEY" in key or "KEY" in key) and len(value) > 12:
            return f"{value[:8]}...{value[-4:]}"

        return value
