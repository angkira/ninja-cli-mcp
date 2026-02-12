"""
Pydantic configuration schemas for the ninja configuration system.

These models define the complete configuration structure for ninja,
including component settings, operator configurations, and preferences.
All models use strict validation and comprehensive type hints.

Architecture Version: 2.0.0
Design Document: .agent/CONFIG_ARCHITECTURE_DESIGN.md
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator


# ============================================================================
# Enums and Constants
# ============================================================================


class OperatorType(str, Enum):
    """Available operator types for components."""

    OPENCODE = "opencode"
    AIDER = "aider"
    CLAUDE = "claude"
    GEMINI = "gemini"
    PERPLEXITY = "perplexity"


class EditFormat(str, Enum):
    """Aider edit format options."""

    DIFF = "diff"
    WHOLE = "whole"
    UDIFF = "udiff"


class CostQualityPreference(str, Enum):
    """Cost vs quality preference levels."""

    COST = "cost"
    BALANCED = "balanced"
    QUALITY = "quality"


class SearchProvider(str, Enum):
    """Available search providers."""

    DUCKDUCKGO = "duckduckgo"
    SERPER = "serper"
    PERPLEXITY = "perplexity"


# Supported config versions
SUPPORTED_VERSIONS = ["2.0.0"]

# Default daemon ports
DEFAULT_DAEMON_PORTS = {
    "coder": 8100,
    "researcher": 8101,
    "secretary": 8102,
    "prompts": 8107,
}


# ============================================================================
# Operator Settings Models
# ============================================================================


class OpenCodeProviderRouting(BaseModel):
    """
    Provider routing configuration for OpenCode.

    Defines the order in which providers should be tried and whether
    fallbacks are allowed when primary provider fails.

    Examples:
        >>> routing = OpenCodeProviderRouting(
        ...     order=["anthropic", "openrouter"],
        ...     allow_fallbacks=True
        ... )
    """

    order: list[str] = Field(
        default=["anthropic"],
        min_length=1,
        description="Provider preference order (first = primary)",
        examples=[["anthropic", "openrouter"], ["google", "anthropic"]],
    )
    allow_fallbacks: bool = Field(
        default=True,
        description="Allow fallback to other providers on failure",
    )

    @field_validator("order")
    @classmethod
    def validate_order(cls, v: list[str]) -> list[str]:
        """Ensure provider order is not empty and has no duplicates."""
        if not v:
            raise ValueError("Provider order cannot be empty")
        if len(v) != len(set(v)):
            raise ValueError("Provider order contains duplicates")
        return v


class OpenCodeOperatorSettings(BaseModel):
    """
    OpenCode-specific operator settings.

    Configures the OpenCode CLI behavior including provider selection,
    routing, custom models, and experimental features.

    Examples:
        >>> settings = OpenCodeOperatorSettings(
        ...     provider="anthropic",
        ...     provider_routing=OpenCodeProviderRouting(
        ...         order=["anthropic", "openrouter"],
        ...         allow_fallbacks=True
        ...     ),
        ...     experimental_models=False
        ... )
    """

    provider: str = Field(
        default="anthropic",
        description="Primary provider to use",
        examples=["anthropic", "openrouter", "google", "openai"],
    )
    provider_routing: OpenCodeProviderRouting | None = Field(
        default=None,
        description="Provider routing configuration (None = use provider only)",
    )
    custom_models: list[str] = Field(
        default_factory=list,
        description="Custom model IDs to add to available models",
        examples=[
            ["anthropic/claude-custom-model", "openai/gpt-custom"],
            [],
        ],
    )
    experimental_models: bool = Field(
        default=False,
        description="Enable experimental/preview models",
    )

    @model_validator(mode="after")
    def validate_routing_consistency(self) -> OpenCodeOperatorSettings:
        """Ensure provider is in routing order if routing is configured."""
        if self.provider_routing and self.provider not in self.provider_routing.order:
            raise ValueError(
                f"Primary provider '{self.provider}' must be in routing order"
            )
        return self


class AiderOperatorSettings(BaseModel):
    """
    Aider-specific operator settings.

    Configures Aider CLI behavior for code editing, commits, and formatting.

    Examples:
        >>> settings = AiderOperatorSettings(
        ...     edit_format="diff",
        ...     auto_commits=True,
        ...     dirty_commits=True
        ... )
    """

    edit_format: EditFormat = Field(
        default=EditFormat.DIFF,
        description="Edit format for code changes",
    )
    auto_commits: bool = Field(
        default=True,
        description="Enable automatic commits after changes",
    )
    dirty_commits: bool = Field(
        default=True,
        description="Allow commits with uncommitted changes",
    )


class GeminiOperatorSettings(BaseModel):
    """
    Gemini CLI operator settings.

    Currently minimal as Gemini CLI has limited configuration options.
    Reserved for future expansion.

    Examples:
        >>> settings = GeminiOperatorSettings()
    """

    # Gemini has minimal settings currently
    # Reserved for future expansion
    pass


class ClaudeCodeOperatorSettings(BaseModel):
    """
    Claude Code operator settings.

    Currently minimal as Claude Code has limited configuration options.
    Reserved for future expansion.

    Examples:
        >>> settings = ClaudeCodeOperatorSettings()
    """

    # Claude Code has minimal settings currently
    # Reserved for future expansion
    pass


class PerplexityOperatorSettings(BaseModel):
    """
    Perplexity API operator settings.

    Configures Perplexity AI search and reasoning behavior.
    Reserved for future expansion.

    Examples:
        >>> settings = PerplexityOperatorSettings()
    """

    # Perplexity has minimal settings currently
    # Reserved for future expansion
    pass


# Union type for all operator settings
OperatorSettingsType = (
    OpenCodeOperatorSettings
    | AiderOperatorSettings
    | GeminiOperatorSettings
    | ClaudeCodeOperatorSettings
    | PerplexityOperatorSettings
)


# ============================================================================
# Model Configuration
# ============================================================================


class ModelConfiguration(BaseModel):
    """
    Model configuration for a component.

    Defines which models to use for different task complexities.
    Only 'default' is required; others are optional overrides.

    Examples:
        >>> config = ModelConfiguration(
        ...     default="anthropic/claude-sonnet-4-5",
        ...     quick="anthropic/claude-haiku-4-5",
        ...     heavy="anthropic/claude-opus-4",
        ...     parallel="anthropic/claude-haiku-4-5"
        ... )
    """

    default: str = Field(
        ...,
        min_length=1,
        description="Default model for standard tasks",
        examples=[
            "anthropic/claude-sonnet-4-5",
            "google/gemini-2.0-flash",
            "openai/gpt-4",
        ],
    )
    quick: str | None = Field(
        None,
        description="Fast model for simple tasks (falls back to default)",
        examples=["anthropic/claude-haiku-4-5", "google/gemini-2.0-flash"],
    )
    heavy: str | None = Field(
        None,
        description="Powerful model for complex tasks (falls back to default)",
        examples=["anthropic/claude-opus-4", "openai/gpt-4"],
    )
    parallel: str | None = Field(
        None,
        description="Model for parallel tasks (falls back to quick or default)",
        examples=["anthropic/claude-haiku-4-5"],
    )

    @field_validator("default", "quick", "heavy", "parallel")
    @classmethod
    def validate_model_id(cls, v: str | None) -> str | None:
        """Ensure model IDs are non-empty strings."""
        if v is not None and not v.strip():
            raise ValueError("Model ID cannot be empty or whitespace")
        return v


# ============================================================================
# Component Configuration
# ============================================================================


class ComponentConfig(BaseModel):
    """
    Configuration for a single component (coder, researcher, secretary).

    Each component has an operator, operator-specific settings, and model
    configuration. Some components have additional settings like search_provider.

    Examples:
        >>> config = ComponentConfig(
        ...     operator="opencode",
        ...     operator_settings={
        ...         "opencode": OpenCodeOperatorSettings(
        ...             provider="anthropic",
        ...             provider_routing=OpenCodeProviderRouting(
        ...                 order=["anthropic", "openrouter"],
        ...                 allow_fallbacks=True
        ...             )
        ...         )
        ...     },
        ...     models=ModelConfiguration(
        ...         default="anthropic/claude-sonnet-4-5",
        ...         quick="anthropic/claude-haiku-4-5"
        ...     ),
        ...     search_provider="perplexity"
        ... )
    """

    operator: OperatorType = Field(
        ...,
        description="Operator to use for this component",
    )
    operator_settings: dict[str, Any] = Field(
        default_factory=dict,
        description="Operator-specific settings, keyed by operator name",
    )
    models: ModelConfiguration = Field(
        ...,
        description="Model configuration for this component",
    )
    search_provider: SearchProvider | None = Field(
        None,
        description="Search provider (researcher component only)",
    )

    @model_validator(mode="after")
    def validate_operator_settings(self) -> ComponentConfig:
        """Ensure operator settings match the selected operator."""
        if not self.operator_settings:
            return self

        # Check if settings exist for the selected operator
        operator_name = self.operator.value
        if operator_name not in self.operator_settings:
            # This is OK - settings are optional
            return self

        # Validate settings type based on operator
        settings = self.operator_settings[operator_name]
        expected_types = {
            OperatorType.OPENCODE: OpenCodeOperatorSettings,
            OperatorType.AIDER: AiderOperatorSettings,
            OperatorType.GEMINI: GeminiOperatorSettings,
            OperatorType.CLAUDE: ClaudeCodeOperatorSettings,
            OperatorType.PERPLEXITY: PerplexityOperatorSettings,
        }

        expected_type = expected_types.get(self.operator)
        if expected_type and not isinstance(settings, (expected_type, dict)):
            raise ValueError(
                f"Invalid settings type for operator '{operator_name}': "
                f"expected {expected_type.__name__}, got {type(settings).__name__}"
            )

        return self


# ============================================================================
# Daemon Configuration
# ============================================================================


class DaemonConfig(BaseModel):
    """
    Daemon configuration for MCP servers.

    Controls whether MCP daemon is enabled and which ports each
    component server should use.

    Examples:
        >>> config = DaemonConfig(
        ...     enabled=True,
        ...     ports={
        ...         "coder": 8100,
        ...         "researcher": 8101,
        ...         "secretary": 8102,
        ...         "prompts": 8107
        ...     }
        ... )
    """

    enabled: bool = Field(
        default=True,
        description="Enable MCP daemon",
    )
    ports: dict[str, int] = Field(
        default_factory=lambda: DEFAULT_DAEMON_PORTS.copy(),
        description="Port mappings for each component server",
    )

    @field_validator("ports")
    @classmethod
    def validate_ports(cls, v: dict[str, int]) -> dict[str, int]:
        """Ensure all ports are valid and non-conflicting."""
        if not v:
            raise ValueError("Ports configuration cannot be empty")

        # Check port ranges
        for component, port in v.items():
            if not 1024 <= port <= 65535:
                raise ValueError(
                    f"Invalid port {port} for {component}: must be between 1024 and 65535"
                )

        # Check for port conflicts
        ports_list = list(v.values())
        if len(ports_list) != len(set(ports_list)):
            raise ValueError("Port conflict: multiple components using the same port")

        return v


# ============================================================================
# Preferences
# ============================================================================


class Preferences(BaseModel):
    """
    User preferences for ninja behavior.

    Controls global settings like cost/quality tradeoff, auto-updates,
    and telemetry collection.

    Examples:
        >>> prefs = Preferences(
        ...     cost_vs_quality="balanced",
        ...     auto_update=True,
        ...     telemetry=False
        ... )
    """

    cost_vs_quality: CostQualityPreference = Field(
        default=CostQualityPreference.BALANCED,
        description="Cost vs quality preference for model selection",
    )
    auto_update: bool = Field(
        default=True,
        description="Enable automatic updates",
    )
    telemetry: bool = Field(
        default=False,
        description="Enable anonymous usage telemetry",
    )


# ============================================================================
# Root Configuration
# ============================================================================


class NinjaConfig(BaseModel):
    """
    Root configuration schema for ninja.

    This is the top-level configuration object that contains all
    component configurations, daemon settings, and user preferences.

    The configuration is stored in JSON format at ~/.ninja/config.json
    and is validated against this schema on load.

    Examples:
        >>> config = NinjaConfig(
        ...     version="2.0.0",
        ...     components={
        ...         "coder": ComponentConfig(
        ...             operator="opencode",
        ...             operator_settings={
        ...                 "opencode": OpenCodeOperatorSettings(
        ...                     provider="anthropic"
        ...                 )
        ...             },
        ...             models=ModelConfiguration(
        ...                 default="anthropic/claude-sonnet-4-5"
        ...             )
        ...         )
        ...     },
        ...     daemon=DaemonConfig(enabled=True),
        ...     preferences=Preferences(cost_vs_quality="balanced")
        ... )
    """

    version: str = Field(
        default="2.0.0",
        description="Config schema version",
        examples=SUPPORTED_VERSIONS,
    )
    last_updated: datetime = Field(
        default_factory=datetime.now,
        description="Last configuration update timestamp",
    )
    components: dict[str, ComponentConfig] = Field(
        ...,
        min_length=1,
        description="Component configurations (coder, researcher, secretary)",
        examples=[
            {
                "coder": {
                    "operator": "opencode",
                    "operator_settings": {
                        "opencode": {
                            "provider": "anthropic",
                            "provider_routing": {
                                "order": ["anthropic", "openrouter"],
                                "allow_fallbacks": True,
                            },
                        }
                    },
                    "models": {
                        "default": "anthropic/claude-sonnet-4-5",
                        "quick": "anthropic/claude-haiku-4-5",
                    },
                }
            }
        ],
    )
    daemon: DaemonConfig = Field(
        default_factory=DaemonConfig,
        description="Daemon configuration",
    )
    preferences: Preferences = Field(
        default_factory=Preferences,
        description="User preferences",
    )

    @field_validator("version")
    @classmethod
    def validate_version(cls, v: str) -> str:
        """Ensure version is supported."""
        if v not in SUPPORTED_VERSIONS:
            raise ValueError(
                f"Unsupported config version: {v}. "
                f"Supported versions: {', '.join(SUPPORTED_VERSIONS)}"
            )
        return v

    @field_validator("components")
    @classmethod
    def validate_components(cls, v: dict[str, ComponentConfig]) -> dict[str, ComponentConfig]:
        """Ensure at least one component is configured."""
        if not v:
            raise ValueError("At least one component must be configured")

        # Validate known component names
        valid_components = {"coder", "researcher", "secretary"}
        for component_name in v:
            if component_name not in valid_components:
                raise ValueError(
                    f"Unknown component: {component_name}. "
                    f"Valid components: {', '.join(sorted(valid_components))}"
                )

        return v

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "version": "2.0.0",
                    "last_updated": "2026-02-12T01:45:00Z",
                    "components": {
                        "coder": {
                            "operator": "opencode",
                            "operator_settings": {
                                "opencode": {
                                    "provider": "anthropic",
                                    "provider_routing": {
                                        "order": ["anthropic", "openrouter"],
                                        "allow_fallbacks": True,
                                    },
                                    "custom_models": [],
                                    "experimental_models": False,
                                }
                            },
                            "models": {
                                "default": "anthropic/claude-sonnet-4-5",
                                "quick": "anthropic/claude-haiku-4-5",
                                "heavy": "anthropic/claude-opus-4",
                                "parallel": "anthropic/claude-haiku-4-5",
                            },
                        },
                        "researcher": {
                            "operator": "perplexity",
                            "models": {
                                "default": "sonar-pro",
                            },
                            "search_provider": "perplexity",
                        },
                        "secretary": {
                            "operator": "opencode",
                            "operator_settings": {
                                "opencode": {
                                    "provider": "google",
                                }
                            },
                            "models": {
                                "default": "google/gemini-2.0-flash",
                            },
                        },
                    },
                    "daemon": {
                        "enabled": True,
                        "ports": {
                            "coder": 8100,
                            "researcher": 8101,
                            "secretary": 8102,
                            "prompts": 8107,
                        },
                    },
                    "preferences": {
                        "cost_vs_quality": "balanced",
                        "auto_update": True,
                        "telemetry": False,
                    },
                }
            ]
        }
    }


# ============================================================================
# Helper Functions
# ============================================================================


def create_default_config() -> NinjaConfig:
    """
    Create a default configuration with sensible defaults.

    Returns:
        NinjaConfig: Default configuration instance

    Examples:
        >>> config = create_default_config()
        >>> assert config.version == "2.0.0"
        >>> assert "coder" in config.components
    """
    return NinjaConfig(
        version="2.0.0",
        components={
            "coder": ComponentConfig(
                operator=OperatorType.OPENCODE,
                operator_settings={
                    "opencode": OpenCodeOperatorSettings(
                        provider="anthropic",
                        provider_routing=OpenCodeProviderRouting(
                            order=["anthropic"],
                            allow_fallbacks=True,
                        ),
                    )
                },
                models=ModelConfiguration(
                    default="anthropic/claude-sonnet-4-5",
                    quick="anthropic/claude-haiku-4-5",
                    heavy="anthropic/claude-opus-4",
                    parallel="anthropic/claude-haiku-4-5",
                ),
            ),
            "researcher": ComponentConfig(
                operator=OperatorType.PERPLEXITY,
                operator_settings={},
                models=ModelConfiguration(
                    default="sonar-pro",
                ),
                search_provider=SearchProvider.PERPLEXITY,
            ),
            "secretary": ComponentConfig(
                operator=OperatorType.OPENCODE,
                operator_settings={
                    "opencode": OpenCodeOperatorSettings(
                        provider="google",
                    )
                },
                models=ModelConfiguration(
                    default="google/gemini-2.0-flash",
                ),
            ),
        },
        daemon=DaemonConfig(
            enabled=True,
            ports=DEFAULT_DAEMON_PORTS.copy(),
        ),
        preferences=Preferences(
            cost_vs_quality=CostQualityPreference.BALANCED,
            auto_update=True,
            telemetry=False,
        ),
    )


def validate_config_dict(config_dict: dict[str, Any]) -> NinjaConfig:
    """
    Validate a configuration dictionary and return a NinjaConfig instance.

    Args:
        config_dict: Dictionary containing configuration data

    Returns:
        NinjaConfig: Validated configuration instance

    Raises:
        ValidationError: If configuration is invalid

    Examples:
        >>> config_dict = {
        ...     "version": "2.0.0",
        ...     "components": {
        ...         "coder": {
        ...             "operator": "opencode",
        ...             "models": {"default": "anthropic/claude-sonnet-4-5"}
        ...         }
        ...     }
        ... }
        >>> config = validate_config_dict(config_dict)
    """
    return NinjaConfig.model_validate(config_dict)
