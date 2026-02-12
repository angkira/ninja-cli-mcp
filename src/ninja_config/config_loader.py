"""
Configuration loader for ninja-mcp.

This module provides the ConfigLoader class for loading, saving, and managing
the unified JSON configuration file. It replaces the old ConfigManager and
provides a clean interface for configuration management.

Architecture:
    - Infrastructure Layer: Handles file I/O, permissions, and backups
    - Uses Pydantic models from config_schema for validation
    - Implements atomic writes (temp file + rename)
    - Automatic directory creation and permission setting
"""

import json
import shutil
import tempfile
from datetime import datetime
from pathlib import Path

from ninja_config.config_schema import NinjaConfig


class ConfigLoader:
    """
    Unified configuration loader for ninja-mcp.

    This class handles loading and saving the hierarchical JSON configuration,
    with proper validation, backup functionality, and secure file permissions.

    Configuration File Location:
        ~/.ninja/config.json

    Directory Permissions:
        - ~/.ninja: 700 (rwx------)
        - ~/.ninja/config.json: 600 (rw-------)

    Features:
        - Atomic writes (temp file + rename)
        - Automatic backups with timestamps
        - Pydantic validation
        - Graceful handling of missing config
        - Directory auto-creation

    Example:
        >>> loader = ConfigLoader()
        >>> if loader.exists():
        ...     config = loader.load()
        ...     print(f"Loaded config version {config.version}")
        ... else:
        ...     print("No config found, running setup...")
    """

    def __init__(self, config_dir: Path | None = None) -> None:
        """
        Initialize the configuration loader.

        Args:
            config_dir: Optional custom configuration directory.
                       Defaults to ~/.ninja
        """
        self._config_dir = config_dir or (Path.home() / ".ninja")
        self._config_path = self._config_dir / "config.json"
        self._backup_dir = self._config_dir / "config.backup"

    def load(self) -> NinjaConfig:
        """
        Load and validate the configuration file.

        Returns:
            Validated NinjaConfig object

        Raises:
            FileNotFoundError: If config file does not exist
            json.JSONDecodeError: If config file is not valid JSON
            pydantic.ValidationError: If config does not match schema

        Example:
            >>> loader = ConfigLoader()
            >>> config = loader.load()
            >>> print(config.components["coder"].operator)
            opencode
        """
        if not self._config_path.exists():
            raise FileNotFoundError(
                f"Configuration file not found: {self._config_path}\n"
                f"Run 'ninja-config configure' to create initial configuration."
            )

        # Read JSON file
        with self._config_path.open("r", encoding="utf-8") as f:
            config_data = json.load(f)

        # Validate with Pydantic
        config = NinjaConfig.model_validate(config_data)

        return config

    def save(self, config: NinjaConfig) -> None:
        """
        Save configuration to file with atomic write.

        This method:
        1. Creates the config directory if it doesn't exist
        2. Writes to a temporary file first
        3. Sets proper permissions (700 on dir, 600 on file)
        4. Atomically renames temp file to config.json

        Args:
            config: Validated NinjaConfig object to save

        Raises:
            OSError: If file operations fail
            PermissionError: If unable to set permissions

        Example:
            >>> loader = ConfigLoader()
            >>> config = loader.load()
            >>> config.preferences.auto_update = False
            >>> loader.save(config)
        """
        # Ensure directory exists with proper permissions
        self._ensure_config_directory()

        # Convert to JSON with pretty formatting
        config_data = config.model_dump(mode="json")
        config_json = json.dumps(config_data, indent=2, default=str)

        # Write to temporary file first (atomic write)
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=self._config_dir,
            delete=False,
            suffix=".tmp"
        ) as temp_file:
            temp_path = Path(temp_file.name)
            temp_file.write(config_json)
            temp_file.write("\n")  # Ensure trailing newline

        try:
            # Set proper permissions on temp file
            temp_path.chmod(0o600)  # rw-------

            # Atomic rename
            temp_path.rename(self._config_path)

        except Exception:
            # Clean up temp file on error
            if temp_path.exists():
                temp_path.unlink()
            raise

    def exists(self) -> bool:
        """
        Check if configuration file exists.

        Returns:
            True if config.json exists, False otherwise

        Example:
            >>> loader = ConfigLoader()
            >>> if not loader.exists():
            ...     print("Need to run setup")
        """
        return self._config_path.exists()

    def get_config_path(self) -> Path:
        """
        Get the full path to the configuration file.

        Returns:
            Path object pointing to config.json

        Example:
            >>> loader = ConfigLoader()
            >>> print(f"Config location: {loader.get_config_path()}")
            Config location: /Users/username/.ninja/config.json
        """
        return self._config_path

    def backup(self, tag: str | None = None) -> Path:
        """
        Create a timestamped backup of the current configuration.

        Args:
            tag: Optional tag to append to backup filename
                (e.g., "before-migration")

        Returns:
            Path to the created backup file

        Raises:
            FileNotFoundError: If config file does not exist
            OSError: If backup operation fails

        Example:
            >>> loader = ConfigLoader()
            >>> backup_path = loader.backup("before-upgrade")
            >>> print(f"Backup created: {backup_path}")
            Backup created: /Users/username/.ninja/config.backup/config.json.20260212_134500.before-upgrade
        """
        if not self._config_path.exists():
            raise FileNotFoundError(
                f"Cannot backup: configuration file not found: {self._config_path}"
            )

        # Ensure backup directory exists
        self._backup_dir.mkdir(parents=True, exist_ok=True)
        self._backup_dir.chmod(0o700)  # rwx------

        # Generate backup filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_filename = f"config.json.{timestamp}"

        if tag:
            # Sanitize tag (remove non-alphanumeric except dash/underscore)
            safe_tag = "".join(c for c in tag if c.isalnum() or c in "-_")
            backup_filename = f"{backup_filename}.{safe_tag}"

        backup_path = self._backup_dir / backup_filename

        # Copy file
        shutil.copy2(self._config_path, backup_path)
        backup_path.chmod(0o600)  # rw-------

        return backup_path

    def _ensure_config_directory(self) -> None:
        """
        Ensure configuration directory exists with proper permissions.

        Creates ~/.ninja if it doesn't exist and sets permissions to 700.

        Raises:
            OSError: If directory creation fails
            PermissionError: If unable to set permissions
        """
        if not self._config_dir.exists():
            self._config_dir.mkdir(parents=True, exist_ok=True)

        # Set directory permissions: rwx------ (owner only)
        self._config_dir.chmod(0o700)


class ConfigLoaderError(Exception):
    """Base exception for ConfigLoader errors."""
    pass


class ConfigValidationError(ConfigLoaderError):
    """Raised when configuration validation fails."""
    pass


class ConfigMigrationNeededError(ConfigLoaderError):
    """
    Raised when old .env config exists but new config does not.

    This signals that automatic migration should be triggered.
    """
    pass
