#!/usr/bin/env python3
"""
OpenCode Integration Example

This example demonstrates how to use the OpenCode integration module
to sync ninja configuration with OpenCode CLI.

Usage:
    python3 examples/opencode_integration_example.py
"""

import json
import tempfile
from pathlib import Path

from ninja_config.config_schema import (
    ComponentConfig,
    ModelConfiguration,
    NinjaConfig,
    OpenCodeOperatorSettings,
    OpenCodeProviderRouting,
    OperatorType,
)
from ninja_config.opencode_integration import OpenCodeIntegration


def example_basic_setup():
    """Example 1: Basic OpenCode configuration setup."""
    print("\n=== Example 1: Basic OpenCode Setup ===\n")

    # Create a basic ninja config with OpenCode operator
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
                models=ModelConfiguration(
                    default="anthropic/claude-sonnet-4-5",
                    quick="anthropic/claude-haiku-4-5",
                ),
            )
        },
    )

    # Initialize OpenCode integration
    integration = OpenCodeIntegration()

    # Generate OpenCode config
    opencode_config = integration.generate_opencode_config(ninja_config)

    print("Generated OpenCode config:")
    print(json.dumps(opencode_config, indent=2))
    print()


def example_advanced_routing():
    """Example 2: Advanced provider routing configuration."""
    print("\n=== Example 2: Advanced Provider Routing ===\n")

    # Create config with provider routing
    ninja_config = NinjaConfig(
        version="2.0.0",
        components={
            "coder": ComponentConfig(
                operator=OperatorType.OPENCODE,
                operator_settings={
                    "opencode": OpenCodeOperatorSettings(
                        provider="anthropic",
                        provider_routing=OpenCodeProviderRouting(
                            order=["anthropic", "openrouter", "google"],
                            allow_fallbacks=True,
                        ),
                        custom_models=[
                            "anthropic/claude-custom-model",
                            "openai/gpt-custom-model",
                        ],
                        experimental_models=True,
                    )
                },
                models=ModelConfiguration(
                    default="anthropic/claude-sonnet-4-5",
                    quick="anthropic/claude-haiku-4-5",
                    heavy="anthropic/claude-opus-4",
                ),
            )
        },
    )

    # Initialize OpenCode integration
    integration = OpenCodeIntegration()

    # Generate OpenCode config
    opencode_config = integration.generate_opencode_config(ninja_config)

    print("Generated OpenCode config with routing:")
    print(json.dumps(opencode_config, indent=2))
    print()

    print("Key features:")
    print(f"  - Default Provider: {opencode_config['defaultProvider']}")
    print(f"  - Provider Order: {opencode_config['providerRouting']['order']}")
    print(f"  - Custom Models: {list(opencode_config['models'].keys())}")
    print(f"  - Experimental Models: {opencode_config.get('experimentalModels', False)}")
    print()


def example_bidirectional_sync():
    """Example 3: Bidirectional config synchronization."""
    print("\n=== Example 3: Bidirectional Sync ===\n")

    # Create original ninja config
    original_settings = OpenCodeOperatorSettings(
        provider="anthropic",
        provider_routing=OpenCodeProviderRouting(
            order=["anthropic", "openrouter"],
            allow_fallbacks=True,
        ),
        custom_models=["custom-model-1", "custom-model-2"],
        experimental_models=False,
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

    # Initialize OpenCode integration
    integration = OpenCodeIntegration()

    # Step 1: Transform ninja -> OpenCode
    print("Step 1: Transform ninja config to OpenCode format")
    opencode_config = integration.generate_opencode_config(ninja_config)
    print(json.dumps(opencode_config, indent=2))
    print()

    # Step 2: Parse OpenCode -> ninja
    print("Step 2: Parse OpenCode config back to ninja settings")
    parsed_settings = integration.parse_opencode_to_ninja_settings(opencode_config)
    print(f"Provider: {parsed_settings.provider}")
    print(f"Routing Order: {parsed_settings.provider_routing.order}")
    print(f"Custom Models: {parsed_settings.custom_models}")
    print(f"Experimental: {parsed_settings.experimental_models}")
    print()

    # Verify round-trip consistency
    print("Step 3: Verify round-trip consistency")
    assert parsed_settings.provider == original_settings.provider
    assert parsed_settings.provider_routing.order == original_settings.provider_routing.order
    assert set(parsed_settings.custom_models) == set(original_settings.custom_models)
    print("✓ Round-trip successful - all settings preserved!")
    print()


def example_file_operations():
    """Example 4: File I/O operations with temporary directory."""
    print("\n=== Example 4: File Operations ===\n")

    # Use temporary directory for demo
    with tempfile.TemporaryDirectory() as tmp_dir:
        config_dir = Path(tmp_dir) / "ninja_config"

        # Create ninja config
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

        # Initialize integration with custom directory
        integration = OpenCodeIntegration(config_dir=config_dir)

        # Write OpenCode config
        print(f"Writing OpenCode config to: {config_dir / 'config.json'}")
        integration.write_opencode_config(ninja_config)
        print("✓ Config written")
        print()

        # Read back the config
        print("Reading OpenCode config back...")
        read_config = integration.read_opencode_config()
        if read_config:
            print("✓ Config read successfully:")
            print(json.dumps(read_config, indent=2))
            print()

        # Verify file permissions (Unix only)
        config_file = config_dir / "config.json"
        if config_file.exists():
            perms = oct(config_file.stat().st_mode)[-3:]
            print(f"File permissions: {perms} (should be 600)")
            print()


def example_environment_setup():
    """Example 5: Environment variable setup."""
    print("\n=== Example 5: Environment Setup ===\n")

    # Use temporary directory
    with tempfile.TemporaryDirectory() as tmp_dir:
        config_dir = Path(tmp_dir) / "ninja_config"

        # Initialize integration
        integration = OpenCodeIntegration(config_dir=config_dir)

        # Setup environment
        print("Setting up OpenCode environment variables...")
        integration.setup_environment()

        # Display environment variables
        import os

        print(f"OPENCODE_CONFIG: {os.environ.get('OPENCODE_CONFIG')}")
        print(f"OPENCODE_CONFIG_DIR: {os.environ.get('OPENCODE_CONFIG_DIR')}")
        print()
        print("✓ OpenCode will now read from our unified config!")
        print()


def example_complete_workflow():
    """Example 6: Complete workflow from config creation to sync."""
    print("\n=== Example 6: Complete Workflow ===\n")

    # Use temporary directory
    with tempfile.TemporaryDirectory() as tmp_dir:
        config_dir = Path(tmp_dir) / "ninja_config"

        # Step 1: Create ninja config
        print("Step 1: Create ninja configuration")
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
                            custom_models=["my-custom-model"],
                        )
                    },
                    models=ModelConfiguration(
                        default="anthropic/claude-sonnet-4-5",
                        quick="anthropic/claude-haiku-4-5",
                    ),
                )
            },
        )
        print("✓ Ninja config created")
        print()

        # Step 2: Initialize integration
        print("Step 2: Initialize OpenCode integration")
        integration = OpenCodeIntegration(config_dir=config_dir)
        print("✓ Integration initialized")
        print()

        # Step 3: Sync to OpenCode
        print("Step 3: Sync configuration to OpenCode")
        success = integration.sync_to_opencode(ninja_config)
        if success:
            print("✓ Sync successful!")
        else:
            print("✗ Sync failed!")
        print()

        # Step 4: Verify
        print("Step 4: Verify OpenCode config")
        opencode_config = integration.read_opencode_config()
        if opencode_config:
            print(json.dumps(opencode_config, indent=2))
            print()
            print("✓ OpenCode is ready to use!")
        print()


def example_case_conversion():
    """Example 7: Case conversion utilities."""
    print("\n=== Example 7: Case Conversion ===\n")

    test_cases = [
        ("provider_routing", "providerRouting"),
        ("allow_fallbacks", "allowFallbacks"),
        ("custom_models", "customModels"),
        ("experimental_models", "experimentalModels"),
    ]

    print("Snake case → Camel case:")
    for snake, expected_camel in test_cases:
        camel = OpenCodeIntegration.snake_to_camel(snake)
        status = "✓" if camel == expected_camel else "✗"
        print(f"  {status} {snake:25} → {camel}")
    print()

    print("Camel case → Snake case:")
    for expected_snake, camel in test_cases:
        snake = OpenCodeIntegration.camel_to_snake(camel)
        status = "✓" if snake == expected_snake else "✗"
        print(f"  {status} {camel:25} → {snake}")
    print()


def main():
    """Run all examples."""
    print("=" * 70)
    print("OpenCode Integration Examples")
    print("=" * 70)

    try:
        example_basic_setup()
        example_advanced_routing()
        example_bidirectional_sync()
        example_file_operations()
        example_environment_setup()
        example_complete_workflow()
        example_case_conversion()

        print("=" * 70)
        print("All examples completed successfully!")
        print("=" * 70)

    except Exception as e:
        print(f"\n✗ Error running examples: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    main()
