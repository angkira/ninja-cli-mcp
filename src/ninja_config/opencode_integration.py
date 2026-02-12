"""
OpenCode integration for unified ninja configuration.

This module provides bidirectional synchronization between ninja's hierarchical
configuration and OpenCode's expected format. It handles environment variable
setup, config transformation (snake_case <-> camelCase), and file management.

Architecture:
    - Infrastructure Layer: Handles OpenCode-specific config transformations
    - Bidirectional sync capability (ninja -> OpenCode, OpenCode -> ninja)
    - Environment variable management for OpenCode integration
    - Case conversion utilities (snake_case <-> camelCase)

Key Integration Points:
    - Called by ConfigLoader when saving config
    - Called by CLI commands that modify operator settings
    - Environment variables set in daemon startup

Environment Variables:
    - OPENCODE_CONFIG: Points to ~/.ninja/config.json
    - OPENCODE_CONFIG_DIR: Points to ~/.ninja

Reference:
    - .agent/CONFIG_ARCHITECTURE_DESIGN.md section 4
    - OpenCode docs: https://opencode.ai/docs/cli/#environment-variables
"""

import json
import logging
import os
from pathlib import Path
from typing import Any

from ninja_config.config_schema import NinjaConfig, OpenCodeOperatorSettings


logger = logging.getLogger(__name__)


class OpenCodeIntegration:
    """
    Manages OpenCode configuration integration with ninja.

    This class handles:
    1. Environment variable setup for OpenCode
    2. Config transformation from ninja format to OpenCode format
    3. Bidirectional sync (read/write OpenCode configs)
    4. Case conversion (snake_case <-> camelCase)

    OpenCode expects a specific configuration format with camelCase keys,
    while ninja uses snake_case. This class bridges the two formats.

    Examples:
        >>> integration = OpenCodeIntegration()
        >>> integration.setup_environment()  # Set OPENCODE_CONFIG env vars
        >>> integration.sync_to_opencode(ninja_config)  # Write OpenCode config
        >>> opencode_config = integration.read_opencode_config()  # Read back
    """

    def __init__(self, config_dir: Path | None = None) -> None:
        """
        Initialize OpenCode integration.

        Args:
            config_dir: Optional custom configuration directory.
                       Defaults to ~/.ninja
        """
        self._config_dir = config_dir or (Path.home() / ".ninja")
        self._opencode_config_path = self._config_dir / "config.json"

    def setup_environment(self) -> None:
        """
        Set up environment variables required by OpenCode.

        Sets:
            - OPENCODE_CONFIG: Path to our unified config.json
            - OPENCODE_CONFIG_DIR: Path to our config directory

        This method should be called before launching OpenCode CLI to ensure
        it reads from our unified configuration.

        Example:
            >>> integration = OpenCodeIntegration()
            >>> integration.setup_environment()
            >>> # Now OpenCode CLI will read from ~/.ninja/config.json
        """
        # Expand ~ to full path for environment variables
        config_path_str = str(self._opencode_config_path.expanduser().absolute())
        config_dir_str = str(self._config_dir.expanduser().absolute())

        os.environ["OPENCODE_CONFIG"] = config_path_str
        os.environ["OPENCODE_CONFIG_DIR"] = config_dir_str

        logger.info(
            f"Set OPENCODE_CONFIG={config_path_str}, "
            f"OPENCODE_CONFIG_DIR={config_dir_str}"
        )

    def generate_opencode_config(self, ninja_config: NinjaConfig) -> dict[str, Any]:
        """
        Generate OpenCode-compatible configuration from ninja config.

        This transforms ninja's hierarchical snake_case config into OpenCode's
        flat camelCase format. Only processes components using opencode operator.

        Transformation:
            ninja format (snake_case):
                components.coder.operator_settings.opencode:
                    provider: "anthropic"
                    provider_routing:
                        order: ["anthropic", "openrouter"]
                        allow_fallbacks: true
                    custom_models: ["my-model"]
                    experimental_models: false

            OpenCode format (camelCase):
                models:
                    my-model: {}
                defaultProvider: "anthropic"
                providerRouting:
                    order: ["anthropic", "openrouter"]
                    allowFallbacks: true
                experimentalModels: false

        Args:
            ninja_config: Validated NinjaConfig object

        Returns:
            Dictionary in OpenCode format (empty dict if no opencode components)

        Example:
            >>> integration = OpenCodeIntegration()
            >>> opencode_cfg = integration.generate_opencode_config(ninja_config)
            >>> print(opencode_cfg["defaultProvider"])
            anthropic
        """
        opencode_config: dict[str, Any] = {}

        # Find components using opencode operator
        opencode_components = [
            (name, component)
            for name, component in ninja_config.components.items()
            if component.operator.value == "opencode"
        ]

        if not opencode_components:
            logger.debug("No components using opencode operator, returning empty config")
            return opencode_config

        # Use coder component as primary source (if available)
        primary_component = None
        for name, component in opencode_components:
            if name == "coder":
                primary_component = component
                break

        # Fall back to first opencode component if coder not found
        if not primary_component:
            primary_component = opencode_components[0][1]

        # Extract OpenCode settings
        settings_dict = primary_component.operator_settings.get("opencode")
        if not settings_dict:
            logger.debug("No opencode settings found in component")
            return opencode_config

        # Parse settings (handle both dict and OpenCodeOperatorSettings)
        if isinstance(settings_dict, dict):
            settings = OpenCodeOperatorSettings.model_validate(settings_dict)
        elif isinstance(settings_dict, OpenCodeOperatorSettings):
            settings = settings_dict
        else:
            logger.warning(
                f"Invalid opencode settings type: {type(settings_dict)}, "
                "using defaults"
            )
            settings = OpenCodeOperatorSettings()

        # Build OpenCode config structure
        opencode_config = {
            "models": {},
            "defaultProvider": settings.provider,
        }

        # Add provider routing if configured
        if settings.provider_routing:
            opencode_config["providerRouting"] = {
                "order": settings.provider_routing.order,
                "allowFallbacks": settings.provider_routing.allow_fallbacks,
            }

        # Add custom models
        if settings.custom_models:
            for model_name in settings.custom_models:
                opencode_config["models"][model_name] = {}

        # Add experimental models flag if enabled
        if settings.experimental_models:
            opencode_config["experimentalModels"] = True

        logger.info(
            f"Generated OpenCode config: provider={settings.provider}, "
            f"custom_models={len(settings.custom_models)}, "
            f"routing={'enabled' if settings.provider_routing else 'disabled'}"
        )

        return opencode_config

    def write_opencode_config(self, ninja_config: NinjaConfig) -> None:
        """
        Write OpenCode configuration to config file.

        This method:
        1. Generates OpenCode config from ninja config
        2. Writes to ~/.ninja/config.json (atomic write)
        3. Sets proper file permissions (600)

        Note: This writes ONLY the OpenCode-specific config, not the full
        ninja config. The full config is managed by ConfigLoader.

        Args:
            ninja_config: Validated NinjaConfig object

        Raises:
            OSError: If file write fails
            PermissionError: If unable to set permissions

        Example:
            >>> integration = OpenCodeIntegration()
            >>> integration.write_opencode_config(ninja_config)
        """
        # Generate OpenCode config
        opencode_config = self.generate_opencode_config(ninja_config)

        if not opencode_config:
            logger.warning("No OpenCode config to write (no opencode components)")
            return

        # Ensure directory exists
        self._config_dir.mkdir(parents=True, exist_ok=True)
        self._config_dir.chmod(0o700)  # rwx------

        # Write config with pretty formatting
        with self._opencode_config_path.open("w", encoding="utf-8") as f:
            json.dump(opencode_config, f, indent=2)
            f.write("\n")  # Ensure trailing newline

        # Set file permissions
        self._opencode_config_path.chmod(0o600)  # rw-------

        logger.info(f"Wrote OpenCode config to {self._opencode_config_path}")

    def read_opencode_config(self) -> dict[str, Any] | None:
        """
        Read existing OpenCode configuration from file.

        Attempts to read the OpenCode config file if it exists. This can be
        used to sync changes made directly by OpenCode back to ninja config.

        Returns:
            Dictionary containing OpenCode config, or None if file doesn't exist
            or is invalid JSON

        Example:
            >>> integration = OpenCodeIntegration()
            >>> config = integration.read_opencode_config()
            >>> if config:
            ...     print(f"Default provider: {config.get('defaultProvider')}")
        """
        if not self._opencode_config_path.exists():
            logger.debug(f"OpenCode config not found at {self._opencode_config_path}")
            return None

        try:
            with self._opencode_config_path.open("r", encoding="utf-8") as f:
                config = json.load(f)

            logger.info(
                f"Read OpenCode config from {self._opencode_config_path}: "
                f"provider={config.get('defaultProvider')}"
            )
            return config

        except (json.JSONDecodeError, OSError) as e:
            logger.error(f"Failed to read OpenCode config: {e}")
            return None

    def sync_to_opencode(self, ninja_config: NinjaConfig) -> bool:
        """
        Synchronize ninja config to OpenCode format.

        This is the main sync method that should be called whenever ninja
        config is updated and needs to be reflected in OpenCode.

        Steps:
        1. Set up environment variables
        2. Generate OpenCode config
        3. Write to file

        Args:
            ninja_config: Validated NinjaConfig object

        Returns:
            True if sync was successful, False otherwise

        Example:
            >>> integration = OpenCodeIntegration()
            >>> success = integration.sync_to_opencode(ninja_config)
            >>> if success:
            ...     print("OpenCode config synced successfully")
        """
        try:
            # Set environment variables
            self.setup_environment()

            # Write OpenCode config
            self.write_opencode_config(ninja_config)

            logger.info("Successfully synced config to OpenCode")
            return True

        except Exception as e:
            logger.error(f"Failed to sync config to OpenCode: {e}", exc_info=True)
            return False

    def parse_opencode_to_ninja_settings(
        self, opencode_config: dict[str, Any]
    ) -> OpenCodeOperatorSettings:
        """
        Parse OpenCode config dict into ninja OpenCodeOperatorSettings.

        This transforms OpenCode's camelCase format back to ninja's snake_case
        Pydantic models. Used for bidirectional sync.

        Transformation (reverse of generate_opencode_config):
            OpenCode format (camelCase):
                defaultProvider: "anthropic"
                providerRouting:
                    order: ["anthropic", "openrouter"]
                    allowFallbacks: true
                experimentalModels: false
                models:
                    my-model: {}

            ninja format (snake_case):
                provider: "anthropic"
                provider_routing:
                    order: ["anthropic", "openrouter"]
                    allow_fallbacks: true
                experimental_models: false
                custom_models: ["my-model"]

        Args:
            opencode_config: OpenCode configuration dictionary

        Returns:
            OpenCodeOperatorSettings object

        Raises:
            ValueError: If required fields are missing or invalid

        Example:
            >>> integration = OpenCodeIntegration()
            >>> opencode_cfg = {"defaultProvider": "anthropic"}
            >>> settings = integration.parse_opencode_to_ninja_settings(opencode_cfg)
            >>> print(settings.provider)
            anthropic
        """
        # Extract provider (defaultProvider -> provider)
        provider = opencode_config.get("defaultProvider", "anthropic")

        # Extract provider routing (providerRouting -> provider_routing)
        provider_routing = None
        if routing := opencode_config.get("providerRouting"):
            from ninja_config.config_schema import OpenCodeProviderRouting

            provider_routing = OpenCodeProviderRouting(
                order=routing.get("order", [provider]),
                allow_fallbacks=routing.get("allowFallbacks", True),
            )

        # Extract custom models (models -> custom_models)
        custom_models = []
        if models := opencode_config.get("models"):
            custom_models = list(models.keys())

        # Extract experimental models flag (experimentalModels -> experimental_models)
        experimental_models = opencode_config.get("experimentalModels", False)

        # Build settings object
        settings = OpenCodeOperatorSettings(
            provider=provider,
            provider_routing=provider_routing,
            custom_models=custom_models,
            experimental_models=experimental_models,
        )

        logger.debug(
            f"Parsed OpenCode config to ninja settings: provider={provider}, "
            f"custom_models={len(custom_models)}"
        )

        return settings

    @staticmethod
    def snake_to_camel(snake_str: str) -> str:
        """
        Convert snake_case string to camelCase.

        Args:
            snake_str: String in snake_case format

        Returns:
            String in camelCase format

        Examples:
            >>> OpenCodeIntegration.snake_to_camel("provider_routing")
            'providerRouting'
            >>> OpenCodeIntegration.snake_to_camel("allow_fallbacks")
            'allowFallbacks'
            >>> OpenCodeIntegration.snake_to_camel("custom_models")
            'customModels'
        """
        components = snake_str.split("_")
        return components[0] + "".join(word.capitalize() for word in components[1:])

    @staticmethod
    def camel_to_snake(camel_str: str) -> str:
        """
        Convert camelCase string to snake_case.

        Args:
            camel_str: String in camelCase format

        Returns:
            String in snake_case format

        Examples:
            >>> OpenCodeIntegration.camel_to_snake("providerRouting")
            'provider_routing'
            >>> OpenCodeIntegration.camel_to_snake("allowFallbacks")
            'allow_fallbacks'
            >>> OpenCodeIntegration.camel_to_snake("customModels")
            'custom_models'
        """
        import re

        # Insert underscore before uppercase letters
        snake = re.sub(r"(?<!^)(?=[A-Z])", "_", camel_str)
        return snake.lower()


class OpenCodeIntegrationError(Exception):
    """Base exception for OpenCode integration errors."""

    pass


class OpenCodeConfigError(OpenCodeIntegrationError):
    """Raised when OpenCode configuration is invalid or missing."""

    pass


class OpenCodeSyncError(OpenCodeIntegrationError):
    """Raised when sync to OpenCode fails."""

    pass
