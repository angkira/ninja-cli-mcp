"""
Configuration manager for ninja-mcp modules.

Provides functionality to view and update configuration settings
stored in ~/.ninja-mcp.env file.
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import sys
from pathlib import Path


logger = logging.getLogger(__name__)

# Module-level guard — migration runs at most once per process.
_migration_done: bool = False


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

        _maybe_migrate(self.config_file)

    def read_config(self) -> dict[str, str]:
        """
        Read configuration from file.

        Returns:
            Dictionary of environment variables.
        """
        config: dict[str, str] = {}

        if not self.config_file.exists():
            return config

        with self.config_file.open() as f:
            for raw_line in f:
                line = raw_line.strip()

                # Skip comments and empty lines
                if not line or line.startswith("#"):
                    continue

                # Parse both "export KEY=value" and "KEY=value" formats
                match = re.match(r"(?:export\s+)?(\w+)=['\"]?(.*?)['\"]?$", line)
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
        lines: list[str] = []

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

                    # Update both export and non-export statements
                    export_match = re.match(r"export\s+(\w+)=", stripped)
                    regular_match = re.match(r"^(\w+)=", stripped) if not export_match else None

                    if export_match:
                        key = export_match.group(1)
                        if key in config:
                            # Update the export value
                            lines.append(f"export {key}='{config[key]}'\n")
                            # Remove from config dict (already processed)
                            del config[key]
                        # else: skip this line (key was deleted or not in config)
                    elif regular_match:
                        key = regular_match.group(1)
                        if key in config:
                            # Update the regular value (preserve non-export format)
                            lines.append(f"{key}={config[key]}\n")
                            # Don't delete from config - may also have export line
                        else:
                            # Keep line if key not in config
                            lines.append(line)
                    else:
                        lines.append(line)
        else:
            # Create new config file
            lines.append("# Ninja MCP Configuration\n")
            lines.append(f"# Generated on {__import__('datetime').datetime.now()}\n")
            lines.append("\n")
            lines.append(
                "# ============================================================================\n"
            )
            lines.append("# Common Configuration\n")
            lines.append(
                "# ============================================================================\n"
            )
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

        For keys in KNOWN_SECRET_NAMES the resolution order is:
        1. SecretStore (keyring → encrypted-file) — highest priority
        2. Existing os.environ value (already set by CI/Docker)
        3. Plaintext value from ~/.ninja-mcp.env (legacy fallback)

        Non-secret keys are injected from the .env file only if not already
        present in os.environ (same as before, only if not already set).
        """
        # Deferred import — avoids pulling keyring into processes that only
        # call read_config/write_config without ever exporting.
        from ninja_config.secrets_store import KNOWN_SECRET_NAMES, default_store

        store = default_store()
        env_config = self.read_config()

        for key, file_value in env_config.items():
            if key in KNOWN_SECRET_NAMES:
                # Resolution chain for secrets
                resolved: str | None = store.get(key)
                source = "store"
                if resolved is None:
                    existing = os.environ.get(key)
                    if existing:
                        resolved = existing
                        source = "env"
                    elif file_value:
                        resolved = file_value
                        source = "file"

                if resolved is not None:
                    if os.environ.get(key) != resolved:
                        os.environ[key] = resolved
                    logger.debug("Secret %s resolved from %s", key, source)
            elif key not in os.environ:
                # Non-secret: inject only if not already in environment
                os.environ[key] = file_value

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


# ---------------------------------------------------------------------------
# Migration helpers (module-level, run at most once per process)
# ---------------------------------------------------------------------------


# Regex matching a secret key at line start, allowing leading whitespace and
# optional "export " prefix:  ^\s*(?:export\s+)?<NAME>\s*=
def _secret_line_pattern(name: str) -> re.Pattern[str]:
    """Compile a regex that matches a .env line declaring the given secret name."""
    return re.compile(r"^\s*(?:export\s+)?" + re.escape(name) + r"\s*=")


def _maybe_migrate(env_file: Path) -> None:
    """Run one-time migration of plaintext secrets from .env into the secret store.

    Decision notes:
    - Backup is created BEFORE any store.set() calls; if store.set raises
      SecretStoreUnavailable the .env is left completely untouched (no backup
      is written in that case — we only write the backup once we know migration
      will succeed).
    - Actually: backup is created only after all secrets are successfully
      written to the store. This keeps the invariant "if backup exists,
      migration completed".
    - Atomic rewrite: write to .env.tmp then os.replace() — never leaves a
      half-written .env.
    - The module-level _migration_done guard prevents re-running on subsequent
      ConfigManager instantiations within the same process.
    """
    global _migration_done
    if _migration_done:
        return
    _migration_done = True  # Set early — even if we bail out, don't retry.

    if not env_file.exists():
        return

    # Deferred import — keyring is not always installed / needed.
    from ninja_config.secrets_store import (
        KNOWN_SECRET_NAMES,
        SecretStoreUnavailable,
        default_store,
    )

    # Read all raw lines preserving original line endings.
    raw_lines = env_file.read_text().splitlines(keepends=True)

    # Identify secret lines: (name, value, index_in_raw_lines)
    secret_line_patterns = {name: _secret_line_pattern(name) for name in KNOWN_SECRET_NAMES}

    secrets_to_migrate: list[tuple[str, str, int]] = []  # (name, value, line_idx)
    for idx, raw_line in enumerate(raw_lines):
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        for name, pattern in secret_line_patterns.items():
            if pattern.match(raw_line):
                # Extract the value — handle quoted and unquoted forms.
                value_match = re.match(
                    r"^\s*(?:export\s+)?" + re.escape(name) + r"\s*=['\"]?(.*?)['\"]?\s*$",
                    raw_line,
                )
                if value_match:
                    value = value_match.group(1)
                    if value:  # Only migrate non-empty values
                        secrets_to_migrate.append((name, value, idx))
                break  # A line can match at most one name

    if not secrets_to_migrate:
        return

    # Attempt to write all secrets to the store. If any fails, abort entirely.
    store = default_store()
    try:
        for name, value, _idx in secrets_to_migrate:
            store.set(name, value)
            logger.debug("Migrated secret %s to store", name)
    except SecretStoreUnavailable:
        logger.debug(
            "SecretStore unavailable; skipping migration of %d secret(s) from %s",
            len(secrets_to_migrate),
            env_file,
        )
        return

    # All secrets written — now create backup (idempotent) and rewrite .env.
    backup_file = env_file.parent / (env_file.name + ".pre-migration.bak")
    if not backup_file.exists():
        shutil.copy2(env_file, backup_file)

    # Line indices of secrets to remove
    lines_to_remove: set[int] = {idx for _name, _value, idx in secrets_to_migrate}
    new_lines = [line for i, line in enumerate(raw_lines) if i not in lines_to_remove]

    tmp_file = env_file.parent / (env_file.name + ".tmp")
    tmp_file.write_text("".join(new_lines))
    tmp_file.chmod(0o600)
    tmp_file.replace(env_file)

    backend_name = store.backend_name()
    n = len(secrets_to_migrate)
    print(
        f"[ninja-mcp] migrated {n} API key{'s' if n != 1 else ''} to {backend_name};"
        f" backup at {backup_file}",
        file=sys.stderr,
    )
