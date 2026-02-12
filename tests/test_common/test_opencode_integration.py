"""
Tests for OpenCode integration module.

Tests cover:
- Environment variable setup
- Config transformation (ninja -> OpenCode format)
- Bidirectional parsing (OpenCode -> ninja format)
- Case conversion utilities (snake_case <-> camelCase)
- File I/O operations
- Error handling
"""

import json
import os
import tempfile
from pathlib import Path

import pytest

from ninja_config.config_schema import (
    ComponentConfig,
    ModelConfiguration,
    NinjaConfig,
    OpenCodeOperatorSettings,
    OpenCodeProviderRouting,
    OperatorType,
)
from ninja_config.opencode_integration import (
    OpenCodeIntegration,
    OpenCodeConfigError,
    OpenCodeSyncError,
)


class TestOpenCodeIntegrationInit:
    """Tests for OpenCodeIntegration initialization."""

    def test_init_default_config_dir(self):
        """Test initialization with default config directory."""
        integration = OpenCodeIntegration()
        expected_dir = Path.home() / ".ninja"
        assert integration._config_dir == expected_dir
        assert integration._opencode_config_path == expected_dir / "config.json"

    def test_init_custom_config_dir(self, tmp_path):
        """Test initialization with custom config directory."""
        custom_dir = tmp_path / "custom_config"
        integration = OpenCodeIntegration(config_dir=custom_dir)
        assert integration._config_dir == custom_dir
        assert integration._opencode_config_path == custom_dir / "config.json"


class TestEnvironmentSetup:
    """Tests for environment variable setup."""

    def test_setup_environment(self, tmp_path):
        """Test setting up OpenCode environment variables."""
        custom_dir = tmp_path / "ninja_config"
        integration = OpenCodeIntegration(config_dir=custom_dir)

        integration.setup_environment()

        # Check environment variables are set
        assert "OPENCODE_CONFIG" in os.environ
        assert "OPENCODE_CONFIG_DIR" in os.environ

        # Check paths are absolute and expanded
        config_path = os.environ["OPENCODE_CONFIG"]
        config_dir = os.environ["OPENCODE_CONFIG_DIR"]

        assert Path(config_path).is_absolute()
        assert Path(config_dir).is_absolute()
        assert config_path == str(custom_dir.absolute() / "config.json")
        assert config_dir == str(custom_dir.absolute())


class TestConfigGeneration:
    """Tests for generating OpenCode config from ninja config."""

    def test_generate_opencode_config_basic(self):
        """Test basic OpenCode config generation."""
        ninja_config = NinjaConfig(
            version="2.0.0",
            components={
                "coder": ComponentConfig(
                    operator=OperatorType.OPENCODE,
                    operator_settings={
                        "opencode": OpenCodeOperatorSettings(
                            provider="anthropic",
                        )
                    },
                    models=ModelConfiguration(default="anthropic/claude-sonnet-4-5"),
                )
            },
        )

        integration = OpenCodeIntegration()
        opencode_config = integration.generate_opencode_config(ninja_config)

        assert opencode_config["defaultProvider"] == "anthropic"
        assert "models" in opencode_config
        assert opencode_config["models"] == {}

    def test_generate_opencode_config_with_routing(self):
        """Test OpenCode config generation with provider routing."""
        ninja_config = NinjaConfig(
            version="2.0.0",
            components={
                "coder": ComponentConfig(
                    operator=OperatorType.OPENCODE,
                    operator_settings={
                        "opencode": OpenCodeOperatorSettings(
                            provider="anthropic",
                            provider_routing=OpenCodeProviderRouting(
                                order=["anthropic", "openrouter"],
                                allow_fallbacks=True,
                            ),
                        )
                    },
                    models=ModelConfiguration(default="anthropic/claude-sonnet-4-5"),
                )
            },
        )

        integration = OpenCodeIntegration()
        opencode_config = integration.generate_opencode_config(ninja_config)

        assert opencode_config["defaultProvider"] == "anthropic"
        assert "providerRouting" in opencode_config
        assert opencode_config["providerRouting"]["order"] == [
            "anthropic",
            "openrouter",
        ]
        assert opencode_config["providerRouting"]["allowFallbacks"] is True

    def test_generate_opencode_config_with_custom_models(self):
        """Test OpenCode config generation with custom models."""
        ninja_config = NinjaConfig(
            version="2.0.0",
            components={
                "coder": ComponentConfig(
                    operator=OperatorType.OPENCODE,
                    operator_settings={
                        "opencode": OpenCodeOperatorSettings(
                            provider="anthropic",
                            custom_models=["custom-model-1", "custom-model-2"],
                        )
                    },
                    models=ModelConfiguration(default="anthropic/claude-sonnet-4-5"),
                )
            },
        )

        integration = OpenCodeIntegration()
        opencode_config = integration.generate_opencode_config(ninja_config)

        assert "models" in opencode_config
        assert "custom-model-1" in opencode_config["models"]
        assert "custom-model-2" in opencode_config["models"]
        assert opencode_config["models"]["custom-model-1"] == {}
        assert opencode_config["models"]["custom-model-2"] == {}

    def test_generate_opencode_config_with_experimental_models(self):
        """Test OpenCode config generation with experimental models flag."""
        ninja_config = NinjaConfig(
            version="2.0.0",
            components={
                "coder": ComponentConfig(
                    operator=OperatorType.OPENCODE,
                    operator_settings={
                        "opencode": OpenCodeOperatorSettings(
                            provider="anthropic",
                            experimental_models=True,
                        )
                    },
                    models=ModelConfiguration(default="anthropic/claude-sonnet-4-5"),
                )
            },
        )

        integration = OpenCodeIntegration()
        opencode_config = integration.generate_opencode_config(ninja_config)

        assert opencode_config.get("experimentalModels") is True

    def test_generate_opencode_config_no_opencode_components(self):
        """Test OpenCode config generation when no opencode components exist."""
        ninja_config = NinjaConfig(
            version="2.0.0",
            components={
                "coder": ComponentConfig(
                    operator=OperatorType.AIDER,
                    operator_settings={},
                    models=ModelConfiguration(default="anthropic/claude-sonnet-4-5"),
                )
            },
        )

        integration = OpenCodeIntegration()
        opencode_config = integration.generate_opencode_config(ninja_config)

        assert opencode_config == {}

    def test_generate_opencode_config_multiple_components(self):
        """Test OpenCode config generation with multiple opencode components."""
        ninja_config = NinjaConfig(
            version="2.0.0",
            components={
                "coder": ComponentConfig(
                    operator=OperatorType.OPENCODE,
                    operator_settings={
                        "opencode": OpenCodeOperatorSettings(
                            provider="anthropic",
                            custom_models=["coder-model"],
                        )
                    },
                    models=ModelConfiguration(default="anthropic/claude-sonnet-4-5"),
                ),
                "secretary": ComponentConfig(
                    operator=OperatorType.OPENCODE,
                    operator_settings={
                        "opencode": OpenCodeOperatorSettings(
                            provider="google",
                            custom_models=["secretary-model"],
                        )
                    },
                    models=ModelConfiguration(default="google/gemini-2.0-flash"),
                ),
            },
        )

        integration = OpenCodeIntegration()
        opencode_config = integration.generate_opencode_config(ninja_config)

        # Should use coder component as primary
        assert opencode_config["defaultProvider"] == "anthropic"
        assert "coder-model" in opencode_config["models"]


class TestConfigParsing:
    """Tests for parsing OpenCode config back to ninja format."""

    def test_parse_opencode_to_ninja_settings_basic(self):
        """Test basic parsing from OpenCode format to ninja settings."""
        opencode_config = {
            "defaultProvider": "anthropic",
            "models": {},
        }

        integration = OpenCodeIntegration()
        settings = integration.parse_opencode_to_ninja_settings(opencode_config)

        assert settings.provider == "anthropic"
        assert settings.provider_routing is None
        assert settings.custom_models == []
        assert settings.experimental_models is False

    def test_parse_opencode_to_ninja_settings_with_routing(self):
        """Test parsing with provider routing."""
        opencode_config = {
            "defaultProvider": "anthropic",
            "providerRouting": {
                "order": ["anthropic", "openrouter"],
                "allowFallbacks": True,
            },
            "models": {},
        }

        integration = OpenCodeIntegration()
        settings = integration.parse_opencode_to_ninja_settings(opencode_config)

        assert settings.provider == "anthropic"
        assert settings.provider_routing is not None
        assert settings.provider_routing.order == ["anthropic", "openrouter"]
        assert settings.provider_routing.allow_fallbacks is True

    def test_parse_opencode_to_ninja_settings_with_custom_models(self):
        """Test parsing with custom models."""
        opencode_config = {
            "defaultProvider": "anthropic",
            "models": {
                "custom-model-1": {},
                "custom-model-2": {},
            },
        }

        integration = OpenCodeIntegration()
        settings = integration.parse_opencode_to_ninja_settings(opencode_config)

        assert settings.provider == "anthropic"
        assert len(settings.custom_models) == 2
        assert "custom-model-1" in settings.custom_models
        assert "custom-model-2" in settings.custom_models

    def test_parse_opencode_to_ninja_settings_with_experimental(self):
        """Test parsing with experimental models flag."""
        opencode_config = {
            "defaultProvider": "anthropic",
            "experimentalModels": True,
            "models": {},
        }

        integration = OpenCodeIntegration()
        settings = integration.parse_opencode_to_ninja_settings(opencode_config)

        assert settings.experimental_models is True

    def test_parse_opencode_to_ninja_settings_defaults(self):
        """Test parsing with minimal config (uses defaults)."""
        opencode_config = {}

        integration = OpenCodeIntegration()
        settings = integration.parse_opencode_to_ninja_settings(opencode_config)

        # Should use defaults
        assert settings.provider == "anthropic"
        assert settings.provider_routing is None
        assert settings.custom_models == []
        assert settings.experimental_models is False


class TestFileOperations:
    """Tests for file I/O operations."""

    def test_write_opencode_config(self, tmp_path):
        """Test writing OpenCode config to file."""
        config_dir = tmp_path / "ninja_config"
        integration = OpenCodeIntegration(config_dir=config_dir)

        ninja_config = NinjaConfig(
            version="2.0.0",
            components={
                "coder": ComponentConfig(
                    operator=OperatorType.OPENCODE,
                    operator_settings={
                        "opencode": OpenCodeOperatorSettings(
                            provider="anthropic",
                            custom_models=["test-model"],
                        )
                    },
                    models=ModelConfiguration(default="anthropic/claude-sonnet-4-5"),
                )
            },
        )

        integration.write_opencode_config(ninja_config)

        # Verify file was created
        config_file = config_dir / "config.json"
        assert config_file.exists()

        # Verify file permissions
        assert oct(config_file.stat().st_mode)[-3:] == "600"

        # Verify file content
        with config_file.open("r") as f:
            written_config = json.load(f)

        assert written_config["defaultProvider"] == "anthropic"
        assert "test-model" in written_config["models"]

    def test_read_opencode_config_exists(self, tmp_path):
        """Test reading existing OpenCode config."""
        config_dir = tmp_path / "ninja_config"
        config_dir.mkdir(parents=True)

        config_file = config_dir / "config.json"
        opencode_config = {
            "defaultProvider": "anthropic",
            "models": {"test-model": {}},
        }

        with config_file.open("w") as f:
            json.dump(opencode_config, f)

        integration = OpenCodeIntegration(config_dir=config_dir)
        read_config = integration.read_opencode_config()

        assert read_config is not None
        assert read_config["defaultProvider"] == "anthropic"
        assert "test-model" in read_config["models"]

    def test_read_opencode_config_not_exists(self, tmp_path):
        """Test reading OpenCode config when file doesn't exist."""
        config_dir = tmp_path / "ninja_config"
        integration = OpenCodeIntegration(config_dir=config_dir)

        read_config = integration.read_opencode_config()

        assert read_config is None

    def test_read_opencode_config_invalid_json(self, tmp_path):
        """Test reading OpenCode config with invalid JSON."""
        config_dir = tmp_path / "ninja_config"
        config_dir.mkdir(parents=True)

        config_file = config_dir / "config.json"
        with config_file.open("w") as f:
            f.write("{invalid json")

        integration = OpenCodeIntegration(config_dir=config_dir)
        read_config = integration.read_opencode_config()

        assert read_config is None


class TestSyncOperations:
    """Tests for sync operations."""

    def test_sync_to_opencode_success(self, tmp_path):
        """Test successful sync to OpenCode."""
        config_dir = tmp_path / "ninja_config"
        integration = OpenCodeIntegration(config_dir=config_dir)

        ninja_config = NinjaConfig(
            version="2.0.0",
            components={
                "coder": ComponentConfig(
                    operator=OperatorType.OPENCODE,
                    operator_settings={
                        "opencode": OpenCodeOperatorSettings(
                            provider="anthropic",
                        )
                    },
                    models=ModelConfiguration(default="anthropic/claude-sonnet-4-5"),
                )
            },
        )

        result = integration.sync_to_opencode(ninja_config)

        assert result is True
        assert (config_dir / "config.json").exists()

        # Verify environment variables were set
        assert "OPENCODE_CONFIG" in os.environ
        assert "OPENCODE_CONFIG_DIR" in os.environ

    def test_sync_to_opencode_no_opencode_components(self, tmp_path):
        """Test sync when no opencode components exist."""
        config_dir = tmp_path / "ninja_config"
        integration = OpenCodeIntegration(config_dir=config_dir)

        ninja_config = NinjaConfig(
            version="2.0.0",
            components={
                "coder": ComponentConfig(
                    operator=OperatorType.AIDER,
                    operator_settings={},
                    models=ModelConfiguration(default="anthropic/claude-sonnet-4-5"),
                )
            },
        )

        result = integration.sync_to_opencode(ninja_config)

        # Should still succeed (just won't write anything)
        assert result is True


class TestCaseConversion:
    """Tests for case conversion utilities."""

    def test_snake_to_camel(self):
        """Test snake_case to camelCase conversion."""
        assert OpenCodeIntegration.snake_to_camel("provider_routing") == "providerRouting"
        assert OpenCodeIntegration.snake_to_camel("allow_fallbacks") == "allowFallbacks"
        assert OpenCodeIntegration.snake_to_camel("custom_models") == "customModels"
        assert (
            OpenCodeIntegration.snake_to_camel("experimental_models")
            == "experimentalModels"
        )
        assert OpenCodeIntegration.snake_to_camel("default_provider") == "defaultProvider"

    def test_snake_to_camel_single_word(self):
        """Test snake_case to camelCase with single word."""
        assert OpenCodeIntegration.snake_to_camel("provider") == "provider"
        assert OpenCodeIntegration.snake_to_camel("models") == "models"

    def test_camel_to_snake(self):
        """Test camelCase to snake_case conversion."""
        assert OpenCodeIntegration.camel_to_snake("providerRouting") == "provider_routing"
        assert OpenCodeIntegration.camel_to_snake("allowFallbacks") == "allow_fallbacks"
        assert OpenCodeIntegration.camel_to_snake("customModels") == "custom_models"
        assert (
            OpenCodeIntegration.camel_to_snake("experimentalModels")
            == "experimental_models"
        )
        assert OpenCodeIntegration.camel_to_snake("defaultProvider") == "default_provider"

    def test_camel_to_snake_single_word(self):
        """Test camelCase to snake_case with single word."""
        assert OpenCodeIntegration.camel_to_snake("provider") == "provider"
        assert OpenCodeIntegration.camel_to_snake("models") == "models"

    def test_bidirectional_case_conversion(self):
        """Test that case conversion is bidirectional."""
        snake_cases = [
            "provider_routing",
            "allow_fallbacks",
            "custom_models",
            "experimental_models",
        ]

        for snake in snake_cases:
            camel = OpenCodeIntegration.snake_to_camel(snake)
            back_to_snake = OpenCodeIntegration.camel_to_snake(camel)
            assert back_to_snake == snake


class TestIntegrationRoundTrip:
    """Tests for complete round-trip operations."""

    def test_roundtrip_config_transformation(self):
        """Test round-trip: ninja -> OpenCode -> ninja."""
        # Create ninja config
        original_settings = OpenCodeOperatorSettings(
            provider="anthropic",
            provider_routing=OpenCodeProviderRouting(
                order=["anthropic", "openrouter"],
                allow_fallbacks=True,
            ),
            custom_models=["model-1", "model-2"],
            experimental_models=True,
        )

        ninja_config = NinjaConfig(
            version="2.0.0",
            components={
                "coder": ComponentConfig(
                    operator=OperatorType.OPENCODE,
                    operator_settings={"opencode": original_settings},
                    models=ModelConfiguration(default="anthropic/claude-sonnet-4-5"),
                )
            },
        )

        # Transform to OpenCode format
        integration = OpenCodeIntegration()
        opencode_config = integration.generate_opencode_config(ninja_config)

        # Transform back to ninja format
        parsed_settings = integration.parse_opencode_to_ninja_settings(opencode_config)

        # Verify settings match
        assert parsed_settings.provider == original_settings.provider
        assert parsed_settings.provider_routing.order == original_settings.provider_routing.order
        assert (
            parsed_settings.provider_routing.allow_fallbacks
            == original_settings.provider_routing.allow_fallbacks
        )
        assert set(parsed_settings.custom_models) == set(original_settings.custom_models)
        assert parsed_settings.experimental_models == original_settings.experimental_models

    def test_roundtrip_file_operations(self, tmp_path):
        """Test round-trip: save -> read -> parse."""
        config_dir = tmp_path / "ninja_config"
        integration = OpenCodeIntegration(config_dir=config_dir)

        # Create and save ninja config
        ninja_config = NinjaConfig(
            version="2.0.0",
            components={
                "coder": ComponentConfig(
                    operator=OperatorType.OPENCODE,
                    operator_settings={
                        "opencode": OpenCodeOperatorSettings(
                            provider="anthropic",
                            custom_models=["test-model"],
                        )
                    },
                    models=ModelConfiguration(default="anthropic/claude-sonnet-4-5"),
                )
            },
        )

        integration.write_opencode_config(ninja_config)

        # Read back
        read_config = integration.read_opencode_config()
        assert read_config is not None

        # Parse back to ninja settings
        parsed_settings = integration.parse_opencode_to_ninja_settings(read_config)

        # Verify settings match
        original_settings = ninja_config.components["coder"].operator_settings["opencode"]
        assert parsed_settings.provider == original_settings.provider
        assert set(parsed_settings.custom_models) == set(original_settings.custom_models)
