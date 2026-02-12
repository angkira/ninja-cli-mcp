"""
Automatic migration from old .env configuration to new JSON+SQLite format.

This module handles the migration from the legacy ~/.ninja-mcp.env file to the
new unified configuration system with JSON config and encrypted SQLite credentials.

Migration Flow:
    1. Check if ~/.ninja-mcp.env exists and ~/.ninja/config.json doesn't
    2. Backup old .env to ~/.ninja/config.backup/ninja-mcp.env.TIMESTAMP
    3. Parse .env (handle both `export KEY=value` and `KEY=value`)
    4. Extract credentials (API_KEY, KEY, PASSWORD in name)
    5. Build NinjaConfig from old settings
    6. Save credentials via CredentialManager
    7. Save config via ConfigLoader
    8. Rename .env to .env.migrated

Architecture:
    - Application Layer: Migration orchestration logic
    - Uses ConfigLoader for config persistence
    - Uses CredentialManager for credential storage
    - Uses Pydantic models for validation

Design Document: .agent/CONFIG_ARCHITECTURE_DESIGN.md, Section 5
"""

import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from ninja_config.config_loader import ConfigLoader
from ninja_config.config_schema import (
    AiderOperatorSettings,
    ClaudeCodeOperatorSettings,
    ComponentConfig,
    DaemonConfig,
    GeminiOperatorSettings,
    ModelConfiguration,
    NinjaConfig,
    OpenCodeOperatorSettings,
    OpenCodeProviderRouting,
    OperatorType,
    PerplexityOperatorSettings,
    Preferences,
    SearchProvider,
)
from ninja_config.credentials import CredentialManager


# Configure logging
logger = logging.getLogger(__name__)


class MigrationError(Exception):
    """Base exception for migration errors."""

    pass


class ConfigMigrator:
    """
    Migrate old .env configuration to new JSON + SQLite format.

    This class handles the complete migration process including:
    - Backup of old configuration
    - Parsing of .env files
    - Extraction and encryption of credentials
    - Building new configuration structure
    - Saving to new format

    Example:
        >>> migrator = ConfigMigrator()
        >>> if migrator.needs_migration():
        ...     result = migrator.migrate()
        ...     print(f"Migrated {result['credentials_count']} credentials")
    """

    def __init__(
        self,
        old_env_path: Path | None = None,
        config_loader: ConfigLoader | None = None,
        credential_manager: CredentialManager | None = None,
    ) -> None:
        """
        Initialize the configuration migrator.

        Args:
            old_env_path: Path to old .env file (defaults to ~/.ninja-mcp.env)
            config_loader: ConfigLoader instance (created if not provided)
            credential_manager: CredentialManager instance (created if not provided)
        """
        self.old_env_path = old_env_path or (Path.home() / ".ninja-mcp.env")
        self.config_loader = config_loader or ConfigLoader()
        self.credential_manager = credential_manager or CredentialManager()

        self.new_config_dir = Path.home() / ".ninja"
        self.backup_dir = self.new_config_dir / "config.backup"
        self.migration_log_dir = self.new_config_dir / "migrations"

    def needs_migration(self) -> bool:
        """
        Check if migration is needed.

        Migration is needed if the old .env file exists and the new config doesn't.

        Returns:
            True if migration is needed, False otherwise

        Example:
            >>> migrator = ConfigMigrator()
            >>> if migrator.needs_migration():
            ...     print("Migration required")
        """
        has_old_config = self.old_env_path.exists()
        has_new_config = self.config_loader.exists()

        return has_old_config and not has_new_config

    def migrate(self) -> dict[str, Any]:
        """
        Perform complete migration from old .env to new format.

        This method orchestrates the entire migration process:
        1. Backup old configuration
        2. Parse old .env file
        3. Extract credentials
        4. Build new configuration
        5. Save credentials to SQLite
        6. Save config to JSON
        7. Mark old config as migrated
        8. Create migration log

        Returns:
            Dictionary with migration results:
            {
                "old_config": str,  # Path to old config
                "new_config": str,  # Path to new config
                "backup": str,      # Path to backup
                "credentials_count": int,
                "migrated_at": str,
                "success": bool
            }

        Raises:
            MigrationError: If migration fails at any step

        Example:
            >>> migrator = ConfigMigrator()
            >>> result = migrator.migrate()
            >>> print(f"Migration completed: {result['new_config']}")
        """
        try:
            logger.info("Starting configuration migration...")
            print("\n" + "=" * 70)
            print("  NINJA CONFIGURATION MIGRATION")
            print("=" * 70)
            print("\nMigrating from legacy .env to new JSON+SQLite format...\n")

            # Step 1: Backup old config
            logger.info("Backing up old configuration...")
            backup_path = self._backup_old_config()
            print(f"✓ Backed up old config to:\n  {backup_path}\n")

            # Step 2: Parse old env file
            logger.info("Parsing old .env file...")
            old_config = self._parse_old_env()
            print(f"✓ Parsed {len(old_config)} settings from old config\n")

            # Step 3: Extract credentials
            logger.info("Extracting credentials...")
            credentials = self._extract_credentials(old_config)
            print(f"✓ Extracted {len(credentials)} API keys/credentials\n")

            # Step 4: Build new config structure
            logger.info("Building new configuration structure...")
            new_config = self._build_new_config(old_config)
            print("✓ Built new configuration structure\n")

            # Step 5: Save credentials to SQLite
            logger.info("Saving credentials to encrypted database...")
            self._save_credentials(credentials)
            print(f"✓ Saved {len(credentials)} credentials to encrypted database\n")

            # Step 6: Save new config to JSON
            logger.info("Saving configuration to JSON...")
            self.config_loader.save(new_config)
            print(f"✓ Saved configuration to:\n  {self.config_loader.get_config_path()}\n")

            # Step 7: Mark old config as migrated
            logger.info("Marking old config as migrated...")
            self._mark_migrated()
            print("✓ Marked old config as migrated\n")

            # Step 8: Create migration log
            migration_result = {
                "old_config": str(self.old_env_path),
                "new_config": str(self.config_loader.get_config_path()),
                "backup": str(backup_path),
                "credentials_count": len(credentials),
                "migrated_at": datetime.now().isoformat(),
                "success": True,
            }
            self._create_migration_log(migration_result)

            print("=" * 70)
            print("  MIGRATION COMPLETED SUCCESSFULLY!")
            print("=" * 70)
            print(f"\n  Old config: {self.old_env_path} (backed up)")
            print(f"  New config: {self.config_loader.get_config_path()}")
            print(f"  Credentials: {len(credentials)} stored in encrypted database")
            print("\n" + "=" * 70 + "\n")

            logger.info("Migration completed successfully")
            return migration_result

        except Exception as e:
            error_msg = f"Migration failed: {e}"
            logger.error(error_msg, exc_info=True)
            print(f"\n✗ ERROR: {error_msg}\n")
            raise MigrationError(error_msg) from e

    def _backup_old_config(self) -> Path:
        """
        Backup old .env file to backup directory.

        Creates ~/.ninja/config.backup/ directory and copies the old .env file
        with a timestamp suffix.

        Returns:
            Path to the backup file

        Raises:
            MigrationError: If backup fails
        """
        try:
            # Ensure backup directory exists
            self.backup_dir.mkdir(parents=True, exist_ok=True)
            self.backup_dir.chmod(0o700)  # rwx------

            # Generate backup filename with timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_filename = f"ninja-mcp.env.{timestamp}"
            backup_path = self.backup_dir / backup_filename

            # Copy file
            shutil.copy2(self.old_env_path, backup_path)
            backup_path.chmod(0o600)  # rw-------

            logger.info(f"Created backup at {backup_path}")
            return backup_path

        except Exception as e:
            raise MigrationError(f"Failed to backup old config: {e}") from e

    def _parse_old_env(self) -> dict[str, str]:
        """
        Parse old .env file.

        Handles both formats:
        - export KEY=value
        - KEY=value

        Ignores comments and empty lines.

        Returns:
            Dictionary of environment variables

        Raises:
            MigrationError: If parsing fails
        """
        try:
            config: dict[str, str] = {}

            with self.old_env_path.open("r", encoding="utf-8") as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()

                    # Skip empty lines and comments
                    if not line or line.startswith("#"):
                        continue

                    # Parse key=value
                    if "=" not in line:
                        logger.warning(f"Skipping invalid line {line_num}: {line}")
                        continue

                    # Remove 'export ' prefix if present
                    line = line.replace("export ", "", 1).strip()

                    # Split on first '=' only
                    key, value = line.split("=", 1)
                    key = key.strip()
                    value = value.strip()

                    # Remove quotes from value
                    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
                        value = value[1:-1]

                    config[key] = value

            logger.info(f"Parsed {len(config)} settings from {self.old_env_path}")
            return config

        except Exception as e:
            raise MigrationError(f"Failed to parse old .env file: {e}") from e

    def _extract_credentials(self, old_config: dict[str, str]) -> dict[str, str]:
        """
        Extract API keys and credentials from old config.

        Identifies credentials by checking if the key name contains:
        - API_KEY
        - _KEY
        - PASSWORD
        - SECRET
        - TOKEN

        Args:
            old_config: Parsed environment variables

        Returns:
            Dictionary of credential name -> value

        Example:
            >>> old_config = {
            ...     "OPENROUTER_API_KEY": "sk-or-...",
            ...     "NINJA_CODE_BIN": "opencode"
            ... }
            >>> credentials = migrator._extract_credentials(old_config)
            >>> assert "OPENROUTER_API_KEY" in credentials
            >>> assert "NINJA_CODE_BIN" not in credentials
        """
        credentials = {}

        credential_indicators = ["API_KEY", "_KEY", "PASSWORD", "SECRET", "TOKEN"]

        for key, value in old_config.items():
            # Check if this is a credential
            if any(indicator in key.upper() for indicator in credential_indicators):
                credentials[key] = value
                logger.debug(f"Identified credential: {key}")

        logger.info(f"Extracted {len(credentials)} credentials")
        return credentials

    def _build_new_config(self, old_config: dict[str, str]) -> NinjaConfig:
        """
        Build new NinjaConfig from old settings.

        Maps old environment variables to new configuration structure.

        Old -> New Mapping:
            NINJA_CODE_BIN -> components.coder.operator
            NINJA_CODER_MODEL -> components.coder.models.default
            NINJA_MODEL_QUICK -> components.coder.models.quick
            NINJA_MODEL_SEQUENTIAL -> components.coder.models.heavy
            NINJA_CODER_PROVIDER -> components.coder.operator_settings.opencode.provider
            NINJA_SEARCH_PROVIDER -> components.researcher.search_provider

        Args:
            old_config: Parsed environment variables

        Returns:
            Validated NinjaConfig instance

        Raises:
            MigrationError: If config building fails
        """
        try:
            components: dict[str, ComponentConfig] = {}

            # ===== CODER COMPONENT =====
            coder_operator_str = old_config.get("NINJA_CODE_BIN", "opencode")
            coder_operator = self._parse_operator_type(coder_operator_str)
            coder_provider = old_config.get("NINJA_CODER_PROVIDER", "anthropic")

            # Build operator settings based on operator type
            coder_operator_settings = self._build_operator_settings(
                coder_operator, coder_provider, old_config
            )

            components["coder"] = ComponentConfig(
                operator=coder_operator,
                operator_settings=coder_operator_settings,
                models=ModelConfiguration(
                    default=old_config.get(
                        "NINJA_CODER_MODEL", "anthropic/claude-sonnet-4-5"
                    ),
                    quick=old_config.get("NINJA_MODEL_QUICK"),
                    heavy=old_config.get("NINJA_MODEL_SEQUENTIAL"),
                    parallel=old_config.get("NINJA_MODEL_PARALLEL"),
                ),
            )

            # ===== RESEARCHER COMPONENT =====
            researcher_operator_str = old_config.get("NINJA_RESEARCHER_OPERATOR", "perplexity")
            researcher_operator = self._parse_operator_type(researcher_operator_str)

            search_provider_str = old_config.get("NINJA_SEARCH_PROVIDER", "duckduckgo")
            search_provider = self._parse_search_provider(search_provider_str)

            components["researcher"] = ComponentConfig(
                operator=researcher_operator,
                operator_settings={},
                models=ModelConfiguration(
                    default=old_config.get("NINJA_RESEARCHER_MODEL", "sonar-pro")
                ),
                search_provider=search_provider,
            )

            # ===== SECRETARY COMPONENT =====
            secretary_operator_str = old_config.get("NINJA_SECRETARY_OPERATOR", "opencode")
            secretary_operator = self._parse_operator_type(secretary_operator_str)
            secretary_provider = old_config.get("NINJA_SECRETARY_PROVIDER", "google")

            secretary_operator_settings = self._build_operator_settings(
                secretary_operator, secretary_provider, old_config
            )

            components["secretary"] = ComponentConfig(
                operator=secretary_operator,
                operator_settings=secretary_operator_settings,
                models=ModelConfiguration(
                    default=old_config.get(
                        "NINJA_SECRETARY_MODEL", "google/gemini-2.0-flash"
                    )
                ),
            )

            # ===== DAEMON CONFIGURATION =====
            daemon_enabled = old_config.get("NINJA_ENABLE_DAEMON", "true").lower() == "true"

            daemon = DaemonConfig(
                enabled=daemon_enabled,
                ports={
                    "coder": int(old_config.get("NINJA_CODER_PORT", "8100")),
                    "researcher": int(old_config.get("NINJA_RESEARCHER_PORT", "8101")),
                    "secretary": int(old_config.get("NINJA_SECRETARY_PORT", "8102")),
                    "prompts": int(old_config.get("NINJA_PROMPTS_PORT", "8107")),
                },
            )

            # ===== PREFERENCES =====
            preferences = Preferences(
                cost_vs_quality="balanced",
                auto_update=True,
                telemetry=False,
            )

            # ===== BUILD ROOT CONFIG =====
            config = NinjaConfig(
                version="2.0.0",
                components=components,
                daemon=daemon,
                preferences=preferences,
            )

            logger.info("Built new configuration structure")
            return config

        except Exception as e:
            raise MigrationError(f"Failed to build new config: {e}") from e

    def _build_operator_settings(
        self, operator: OperatorType, provider: str, old_config: dict[str, str]
    ) -> dict[str, Any]:
        """
        Build operator-specific settings.

        Args:
            operator: Operator type
            provider: Provider name
            old_config: Old configuration dictionary

        Returns:
            Dictionary of operator settings keyed by operator name
        """
        settings: dict[str, Any] = {}

        if operator == OperatorType.OPENCODE:
            settings["opencode"] = OpenCodeOperatorSettings(
                provider=provider,
                provider_routing=OpenCodeProviderRouting(
                    order=[provider],
                    allow_fallbacks=True,
                ),
                custom_models=[],
                experimental_models=False,
            )
        elif operator == OperatorType.AIDER:
            settings["aider"] = AiderOperatorSettings(
                edit_format="diff",
                auto_commits=True,
                dirty_commits=True,
            )
        elif operator == OperatorType.GEMINI:
            settings["gemini"] = GeminiOperatorSettings()
        elif operator == OperatorType.CLAUDE:
            settings["claude"] = ClaudeCodeOperatorSettings()
        elif operator == OperatorType.PERPLEXITY:
            settings["perplexity"] = PerplexityOperatorSettings()

        return settings

    def _parse_operator_type(self, operator_str: str) -> OperatorType:
        """
        Parse operator type from string.

        Args:
            operator_str: Operator string (e.g., "opencode", "aider")

        Returns:
            OperatorType enum value

        Raises:
            MigrationError: If operator is invalid
        """
        operator_map = {
            "opencode": OperatorType.OPENCODE,
            "aider": OperatorType.AIDER,
            "claude": OperatorType.CLAUDE,
            "gemini": OperatorType.GEMINI,
            "perplexity": OperatorType.PERPLEXITY,
        }

        operator_lower = operator_str.lower()
        if operator_lower not in operator_map:
            logger.warning(
                f"Unknown operator '{operator_str}', defaulting to 'opencode'"
            )
            return OperatorType.OPENCODE

        return operator_map[operator_lower]

    def _parse_search_provider(self, provider_str: str) -> SearchProvider:
        """
        Parse search provider from string.

        Args:
            provider_str: Provider string (e.g., "duckduckgo", "serper")

        Returns:
            SearchProvider enum value
        """
        provider_map = {
            "duckduckgo": SearchProvider.DUCKDUCKGO,
            "serper": SearchProvider.SERPER,
            "perplexity": SearchProvider.PERPLEXITY,
        }

        provider_lower = provider_str.lower()
        if provider_lower not in provider_map:
            logger.warning(
                f"Unknown search provider '{provider_str}', defaulting to 'duckduckgo'"
            )
            return SearchProvider.DUCKDUCKGO

        return provider_map[provider_lower]

    def _save_credentials(self, credentials: dict[str, str]) -> None:
        """
        Save credentials to encrypted SQLite database.

        Args:
            credentials: Dictionary of credential name -> value

        Raises:
            MigrationError: If credential storage fails
        """
        try:
            for name, value in credentials.items():
                provider = self._guess_provider(name)
                self.credential_manager.set(name, value, provider=provider)
                logger.debug(f"Saved credential '{name}' with provider '{provider}'")

            logger.info(f"Saved {len(credentials)} credentials to database")

        except Exception as e:
            raise MigrationError(f"Failed to save credentials: {e}") from e

    def _guess_provider(self, key_name: str) -> str:
        """
        Guess provider from credential key name.

        Analyzes the key name to determine which provider it belongs to.

        Args:
            key_name: Credential key name (e.g., "OPENROUTER_API_KEY")

        Returns:
            Provider name (lowercase)

        Example:
            >>> migrator = ConfigMigrator()
            >>> assert migrator._guess_provider("OPENROUTER_API_KEY") == "openrouter"
            >>> assert migrator._guess_provider("ANTHROPIC_API_KEY") == "anthropic"
            >>> assert migrator._guess_provider("GOOGLE_API_KEY") == "google"
        """
        key_upper = key_name.upper()

        # Provider mapping
        provider_keywords = {
            "openrouter": ["OPENROUTER"],
            "anthropic": ["ANTHROPIC", "CLAUDE"],
            "openai": ["OPENAI", "GPT"],
            "google": ["GOOGLE", "GEMINI"],
            "perplexity": ["PERPLEXITY"],
            "serper": ["SERPER"],
            "zai": ["ZHIPU", "ZAI"],
        }

        for provider, keywords in provider_keywords.items():
            if any(keyword in key_upper for keyword in keywords):
                logger.debug(f"Guessed provider '{provider}' for key '{key_name}'")
                return provider

        logger.debug(f"Could not guess provider for key '{key_name}', using 'unknown'")
        return "unknown"

    def _mark_migrated(self) -> None:
        """
        Mark old config as migrated by renaming it.

        Renames ~/.ninja-mcp.env to ~/.ninja-mcp.env.migrated

        Raises:
            MigrationError: If renaming fails
        """
        try:
            migrated_path = self.old_env_path.with_suffix(".env.migrated")
            self.old_env_path.rename(migrated_path)
            logger.info(f"Marked old config as migrated: {migrated_path}")

        except Exception as e:
            raise MigrationError(f"Failed to mark old config as migrated: {e}") from e

    def _create_migration_log(self, result: dict[str, Any]) -> None:
        """
        Create migration log file.

        Logs migration details to ~/.ninja/migrations/YYYYMMDD_from_env.log

        Args:
            result: Migration result dictionary

        Raises:
            MigrationError: If log creation fails
        """
        try:
            # Ensure migration log directory exists
            self.migration_log_dir.mkdir(parents=True, exist_ok=True)
            self.migration_log_dir.chmod(0o700)  # rwx------

            # Generate log filename
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            log_filename = f"{timestamp}_from_env.log"
            log_path = self.migration_log_dir / log_filename

            # Write log
            with log_path.open("w", encoding="utf-8") as f:
                f.write("=" * 70 + "\n")
                f.write("NINJA CONFIGURATION MIGRATION LOG\n")
                f.write("=" * 70 + "\n\n")

                for key, value in result.items():
                    f.write(f"{key}: {value}\n")

                f.write("\n" + "=" * 70 + "\n")

            log_path.chmod(0o600)  # rw-------
            logger.info(f"Created migration log: {log_path}")

        except Exception as e:
            # Don't fail migration if log creation fails
            logger.warning(f"Failed to create migration log: {e}")
