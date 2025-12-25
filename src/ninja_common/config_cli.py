#!/usr/bin/env python3
"""
ninja-config CLI tool for managing configuration.

Allows users to view and update Ninja MCP configuration settings
after installation.
"""

from __future__ import annotations

import argparse
import sys

import httpx

from ninja_common.config_manager import ConfigManager


def print_colored(text: str, color: str = "") -> None:
    """
    Print colored text.

    Args:
        text: Text to print.
        color: Color code (green, yellow, red, cyan, dim).
    """
    colors = {
        "green": "\033[0;32m",
        "yellow": "\033[1;33m",
        "red": "\033[0;31m",
        "cyan": "\033[0;36m",
        "blue": "\033[0;34m",
        "magenta": "\033[0;35m",
        "bold": "\033[1m",
        "dim": "\033[2m",
        "nc": "\033[0m",
    }

    if color in colors:
        print(f"{colors[color]}{text}{colors['nc']}")
    else:
        print(text)


def print_header() -> None:
    """Print the CLI header."""
    print_colored("╔══════════════════════════════════════════════════════════╗", "magenta")
    print_colored("║                                                          ║", "magenta")
    print_colored("║              🥷 NINJA CONFIG MANAGER                    ║", "cyan")
    print_colored("║                                                          ║", "magenta")
    print_colored("╚══════════════════════════════════════════════════════════╝", "magenta")
    print()


def cmd_list(args: argparse.Namespace) -> None:
    """
    List all configuration values.

    Args:
        args: Command arguments.
    """
    config_mgr = ConfigManager(args.config)
    config = config_mgr.list_all()

    if not config:
        print_colored("No configuration found.", "yellow")
        print_colored(f"Config file: {config_mgr.config_file}", "dim")
        print()
        print_colored("Run the installer to create configuration:", "dim")
        print_colored("  ./scripts/install_interactive.sh", "dim")
        return

    print_colored("Current Configuration:", "bold")
    print_colored("─" * 60, "dim")
    print()

    # Group by module
    sections = {
        "Common": [],
        "Coder": [],
        "Researcher": [],
        "Secretary": [],
        "Other": [],
    }

    for key, value in sorted(config.items()):
        # Determine section
        if "CODER" in key or key == "NINJA_CODE_BIN":
            section = "Coder"
        elif "RESEARCHER" in key or "SEARCH" in key or "SERPER" in key or "PERPLEXITY" in key:
            section = "Researcher"
        elif "SECRETARY" in key:
            section = "Secretary"
        elif "OPENROUTER" in key or "OPENAI" in key:
            section = "Common"
        else:
            section = "Other"

        # Mask sensitive values
        if "API_KEY" in key or "KEY" in key:
            if len(value) > 12:
                display_value = f"{value[:8]}...{value[-4:]}"
            else:
                display_value = "***"
        else:
            display_value = value

        sections[section].append((key, display_value))

    # Print sections
    for section_name in ["Common", "Coder", "Researcher", "Secretary", "Other"]:
        items = sections[section_name]
        if not items:
            continue

        print_colored(f"{section_name}:", "cyan")
        for key, value in items:
            print(f"  {key}: {value}")
        print()

    print_colored("─" * 60, "dim")
    print_colored(f"Config file: {config_mgr.config_file}", "dim")


def cmd_get(args: argparse.Namespace) -> None:
    """
    Get a configuration value.

    Args:
        args: Command arguments.
    """
    config_mgr = ConfigManager(args.config)
    value = config_mgr.get(args.key)

    if value is None:
        print_colored(f"Configuration key '{args.key}' not found.", "red")
        sys.exit(1)

    if args.mask:
        value = config_mgr.get_masked(args.key)

    print(value)


def cmd_set(args: argparse.Namespace) -> None:
    """
    Set a configuration value.

    Args:
        args: Command arguments.
    """
    config_mgr = ConfigManager(args.config)

    # Validate model if it's a model key
    if "MODEL" in args.key and args.validate:
        api_key = config_mgr.get("OPENROUTER_API_KEY")
        if api_key and not validate_openrouter_model(args.value, api_key):
            print_colored(
                f"Warning: Model '{args.value}' not found in OpenRouter",
                "yellow",
            )
            response = input("Continue anyway? [y/N]: ")
            if not response.lower().startswith("y"):
                print_colored("Aborted.", "yellow")
                return

    config_mgr.set(args.key, args.value)
    print_colored(f"✓ Updated {args.key}", "green")
    print_colored(f"  New value: {args.value}", "dim")
    print()
    print_colored("Restart daemons to apply changes:", "dim")
    print_colored("  ninja-daemon restart all", "dim")


def cmd_set_model(args: argparse.Namespace) -> None:
    """
    Set model for a module.

    Args:
        args: Command arguments.
    """
    config_mgr = ConfigManager(args.config)

    # Map module to config key
    module_keys = {
        "coder": "NINJA_CODER_MODEL",
        "researcher": "NINJA_RESEARCHER_MODEL",
        "secretary": "NINJA_SECRETARY_MODEL",
    }

    if args.module not in module_keys:
        print_colored(f"Invalid module: {args.module}", "red")
        print_colored("Valid modules: coder, researcher, secretary", "dim")
        sys.exit(1)

    key = module_keys[args.module]

    # Validate model
    if args.validate:
        api_key = config_mgr.get("OPENROUTER_API_KEY")
        if api_key and not validate_openrouter_model(args.model, api_key):
            print_colored(
                f"Warning: Model '{args.model}' not found in OpenRouter",
                "yellow",
            )
            response = input("Continue anyway? [y/N]: ")
            if not response.lower().startswith("y"):
                print_colored("Aborted.", "yellow")
                return

    config_mgr.set(key, args.model)
    print_colored(f"✓ Updated {args.module} model to {args.model}", "green")
    print()
    print_colored("Restart daemons to apply changes:", "dim")
    print_colored(f"  ninja-daemon restart {args.module}", "dim")


def cmd_set_search_provider(args: argparse.Namespace) -> None:
    """
    Set search provider for researcher module.

    Args:
        args: Command arguments.
    """
    config_mgr = ConfigManager(args.config)

    # Validate provider
    valid_providers = ["duckduckgo", "serper", "perplexity"]
    if args.provider not in valid_providers:
        print_colored(f"Invalid provider: {args.provider}", "red")
        print_colored(f"Valid providers: {', '.join(valid_providers)}", "dim")
        sys.exit(1)

    # Check API key requirements
    if args.provider == "serper":
        api_key = config_mgr.get("SERPER_API_KEY")
        if not api_key:
            print_colored(
                "Warning: SERPER_API_KEY not configured",
                "yellow",
            )
            print_colored("Get your key from: https://serper.dev", "dim")
            api_key = input("Enter Serper API key (or press Enter to skip): ")
            if api_key:
                config_mgr.set("SERPER_API_KEY", api_key)
            else:
                print_colored("Cannot use Serper without API key.", "red")
                return

    elif args.provider == "perplexity":
        api_key = config_mgr.get("PERPLEXITY_API_KEY")
        if not api_key:
            print_colored(
                "Warning: PERPLEXITY_API_KEY not configured",
                "yellow",
            )
            print_colored("Get your key from: https://www.perplexity.ai/settings/api", "dim")
            api_key = input("Enter Perplexity API key (or press Enter to skip): ")
            if api_key:
                config_mgr.set("PERPLEXITY_API_KEY", api_key)
            else:
                print_colored("Cannot use Perplexity without API key.", "red")
                return

    config_mgr.set("NINJA_SEARCH_PROVIDER", args.provider)
    print_colored(f"✓ Updated search provider to {args.provider}", "green")
    print()
    print_colored("Restart researcher daemon to apply changes:", "dim")
    print_colored("  ninja-daemon restart researcher", "dim")


def cmd_set_api_key(args: argparse.Namespace) -> None:
    """
    Set API key.

    Args:
        args: Command arguments.
    """
    config_mgr = ConfigManager(args.config)

    # Map service to config key
    key_map = {
        "openrouter": "OPENROUTER_API_KEY",
        "serper": "SERPER_API_KEY",
        "perplexity": "PERPLEXITY_API_KEY",
    }

    if args.service not in key_map:
        print_colored(f"Invalid service: {args.service}", "red")
        print_colored(f"Valid services: {', '.join(key_map.keys())}", "dim")
        sys.exit(1)

    key = key_map[args.service]

    # Get API key
    if args.key:
        api_key = args.key
    else:
        # Prompt for API key (hidden input)
        import getpass

        api_key = getpass.getpass(f"Enter {args.service} API key: ")

    if not api_key:
        print_colored("API key cannot be empty.", "red")
        return

    config_mgr.set(key, api_key)
    print_colored(f"✓ Updated {args.service} API key", "green")
    print()
    print_colored("Restart daemons to apply changes:", "dim")
    print_colored("  ninja-daemon restart all", "dim")


def validate_openrouter_model(model_name: str, api_key: str) -> bool:
    """
    Validate that a model exists in OpenRouter.

    Args:
        model_name: Model name to validate.
        api_key: OpenRouter API key.

    Returns:
        True if model is valid, False otherwise.
    """
    try:
        response = httpx.get(
            "https://openrouter.ai/api/v1/models",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            timeout=10.0,
        )
        response.raise_for_status()
        data = response.json()

        # Check if model exists in data
        for model in data.get("data", []):
            if model.get("id") == model_name:
                return True

        return False

    except Exception:
        # If validation fails, return True to avoid blocking user
        return True


def main() -> None:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Ninja MCP Configuration Manager",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # List all configuration
  ninja-config list

  # Get a specific value
  ninja-config get NINJA_CODER_MODEL

  # Set a value
  ninja-config set NINJA_CODER_MODEL anthropic/claude-sonnet-4

  # Set model for a module
  ninja-config model coder anthropic/claude-sonnet-4

  # Set search provider
  ninja-config search-provider serper

  # Set API key
  ninja-config api-key openrouter
        """,
    )

    parser.add_argument(
        "--config",
        help="Path to config file (default: ~/.ninja-mcp.env)",
        default=None,
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # List command
    subparsers.add_parser("list", help="List all configuration values")

    # Get command
    get_parser = subparsers.add_parser("get", help="Get a configuration value")
    get_parser.add_argument("key", help="Configuration key")
    get_parser.add_argument(
        "--mask",
        action="store_true",
        help="Mask sensitive values",
    )

    # Set command
    set_parser = subparsers.add_parser("set", help="Set a configuration value")
    set_parser.add_argument("key", help="Configuration key")
    set_parser.add_argument("value", help="Configuration value")
    set_parser.add_argument(
        "--no-validate",
        dest="validate",
        action="store_false",
        help="Skip validation",
    )

    # Model command
    model_parser = subparsers.add_parser("model", help="Set model for a module")
    model_parser.add_argument(
        "module",
        choices=["coder", "researcher", "secretary"],
        help="Module name",
    )
    model_parser.add_argument("model", help="Model name")
    model_parser.add_argument(
        "--no-validate",
        dest="validate",
        action="store_false",
        help="Skip validation",
    )

    # Search provider command
    search_parser = subparsers.add_parser(
        "search-provider",
        help="Set search provider for researcher",
    )
    search_parser.add_argument(
        "provider",
        choices=["duckduckgo", "serper", "perplexity"],
        help="Search provider name",
    )

    # API key command
    api_key_parser = subparsers.add_parser("api-key", help="Set API key")
    api_key_parser.add_argument(
        "service",
        choices=["openrouter", "serper", "perplexity"],
        help="Service name",
    )
    api_key_parser.add_argument(
        "key",
        nargs="?",
        help="API key (will prompt if not provided)",
    )

    args = parser.parse_args()

    # Print header for all commands except get
    if args.command != "get":
        print()
        print_header()

    # Dispatch to command handler
    if args.command == "list":
        cmd_list(args)
    elif args.command == "get":
        cmd_get(args)
    elif args.command == "set":
        cmd_set(args)
    elif args.command == "model":
        cmd_set_model(args)
    elif args.command == "search-provider":
        cmd_set_search_provider(args)
    elif args.command == "api-key":
        cmd_set_api_key(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
