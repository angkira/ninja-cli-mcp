#!/usr/bin/env python3
"""
ninja-config CLI tool for managing configuration.

Allows users to view and update Ninja MCP configuration settings
after installation.
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

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
            display_value = f"{value[:8]}...{value[-4:]}" if len(value) > 12 else "***"
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
        api_key = getpass.getpass(f"Enter {args.service} API key: ")

    if not api_key:
        print_colored("API key cannot be empty.", "red")
        return

    config_mgr.set(key, api_key)
    print_colored(f"✓ Updated {args.service} API key", "green")
    print()
    print_colored("Restart daemons to apply changes:", "dim")
    print_colored("  ninja-daemon restart all", "dim")


def cmd_doctor(args: argparse.Namespace) -> None:
    """
    Diagnose and fix common configuration issues.

    Args:
        args: Command arguments.
    """
    issues_found = 0
    issues_fixed = 0

    print_colored("Ninja MCP Doctor", "bold")
    print_colored("─" * 60, "dim")
    print()

    # Check 1: API key in environment
    print_colored("Checking API keys...", "cyan")
    api_key = os.environ.get("OPENROUTER_API_KEY") or os.environ.get("OPENAI_API_KEY")

    if api_key:
        if api_key.startswith("sk-or-"):
            print_colored("  ✓ OPENROUTER_API_KEY is set and valid", "green")
        elif api_key.startswith("sk-"):
            print_colored("  ✓ OPENAI_API_KEY is set", "green")
        else:
            print_colored("  ⚠ API key format looks unusual", "yellow")
    else:
        print_colored("  ✗ No API key found in environment", "red")
        issues_found += 1
        print_colored("    Set OPENROUTER_API_KEY or OPENAI_API_KEY", "dim")
    print()

    # Check 2: MCP config file
    print_colored("Checking MCP configuration...", "cyan")
    mcp_config_paths = [
        Path.home() / ".config" / "claude" / "mcp.json",
        Path.home() / ".claude.json",
    ]

    mcp_config = None
    mcp_config_path = None
    for path in mcp_config_paths:
        if path.exists():
            try:
                with path.open() as f:
                    data = json.load(f)
                if "mcpServers" in data:
                    mcp_config = data
                    mcp_config_path = path
                    break
            except json.JSONDecodeError:
                continue

    if mcp_config_path:
        print_colored(f"  ✓ MCP config found: {mcp_config_path}", "green")

        # Check ninja servers
        servers = mcp_config.get("mcpServers", {})
        ninja_servers = ["ninja-coder", "ninja-researcher", "ninja-secretary"]

        for server in ninja_servers:
            if server in servers:
                server_config = servers[server]
                env = server_config.get("env", {})
                server_api_key = env.get("OPENROUTER_API_KEY", "")

                # Check for shell expansion syntax (indicates config issue)
                if server_api_key.startswith("${"):
                    print_colored(f"  ✗ {server}: API key uses shell syntax (won't work)", "red")
                    issues_found += 1

                    if args.fix and api_key:
                        # Fix by replacing with actual value
                        env["OPENROUTER_API_KEY"] = api_key
                        server_config["env"] = env
                        issues_fixed += 1
                        print_colored("    → Fixed: Updated with actual API key", "green")
                elif not server_api_key:
                    print_colored(f"  ⚠ {server}: No API key configured", "yellow")
                else:
                    print_colored(f"  ✓ {server}: API key configured", "green")
            else:
                print_colored(f"  ⚠ {server}: Not registered", "yellow")

        # Write fixes if any
        if issues_fixed > 0 and mcp_config_path:
            with mcp_config_path.open("w") as f:
                json.dump(mcp_config, f, indent=2)
                f.write("\n")
            print()
            print_colored(f"  → Updated {mcp_config_path}", "green")

    else:
        print_colored("  ✗ No MCP config found", "red")
        issues_found += 1
        print_colored("    Run: ninja-config setup-claude", "dim")
    print()

    # Check 3: Dependencies
    print_colored("Checking dependencies...", "cyan")

    # Check aider
    if shutil.which("aider"):
        print_colored("  ✓ aider is installed", "green")
    else:
        print_colored("  ⚠ aider not found (needed for ninja-coder)", "yellow")
        print_colored("    Install: uv tool install aider-chat", "dim")
        issues_found += 1

    # Check uv
    if shutil.which("uv"):
        print_colored("  ✓ uv is installed", "green")
    else:
        print_colored("  ✗ uv not found", "red")
        issues_found += 1
    print()

    # Check 4: Daemon status
    print_colored("Checking daemon status...", "cyan")
    try:
        result = subprocess.run(
            ["ninja-daemon", "status"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            print_colored("  ✓ Daemon is running", "green")
            for line in result.stdout.strip().split("\n")[:5]:
                print_colored(f"    {line}", "dim")
        else:
            print_colored("  ⚠ Daemon not running", "yellow")
            print_colored("    Start with: ninja-daemon start all", "dim")
    except FileNotFoundError:
        print_colored("  ⚠ ninja-daemon not found", "yellow")
    except subprocess.TimeoutExpired:
        print_colored("  ⚠ Daemon check timed out", "yellow")
    except Exception as e:
        print_colored(f"  ⚠ Could not check daemon: {e}", "yellow")
    print()

    # Summary
    print_colored("─" * 60, "dim")
    if issues_found == 0:
        print_colored("✓ All checks passed!", "green")
    else:
        print_colored(f"Found {issues_found} issue(s)", "yellow")
        if issues_fixed > 0:
            print_colored(f"Fixed {issues_fixed} issue(s)", "green")
        if issues_found > issues_fixed and not args.fix:
            print()
            print_colored("Run with --fix to auto-fix issues:", "dim")
            print_colored("  ninja-config doctor --fix", "dim")
    print()


def cmd_setup_claude(args: argparse.Namespace) -> None:
    """
    Setup Claude Code MCP configuration.

    Args:
        args: Command arguments.
    """
    print_colored("Setting up Claude Code MCP configuration...", "cyan")
    print()

    # Determine config path
    claude_config_dir = Path.home() / ".config" / "claude"
    mcp_config_path = claude_config_dir / "mcp.json"

    # Create directory if needed
    claude_config_dir.mkdir(parents=True, exist_ok=True)

    # Load existing config or create new
    if mcp_config_path.exists():
        try:
            with mcp_config_path.open() as f:
                config = json.load(f)
            print_colored(f"  Found existing config: {mcp_config_path}", "dim")
        except json.JSONDecodeError:
            config = {}
            print_colored("  Existing config was invalid, creating new", "yellow")
    else:
        config = {}
        print_colored(f"  Creating new config: {mcp_config_path}", "dim")

    # Ensure mcpServers exists
    if "mcpServers" not in config:
        config["mcpServers"] = {}

    # Get API key
    api_key = os.environ.get("OPENROUTER_API_KEY") or os.environ.get("OPENAI_API_KEY", "")

    if not api_key:
        print_colored("  ⚠ No API key found in environment", "yellow")
        print_colored("  Set OPENROUTER_API_KEY environment variable first", "dim")
        api_key = getpass.getpass("  Enter API key (or press Enter to skip): ")

    # Define servers to register
    servers = {
        "ninja-coder": {
            "command": "ninja-coder",
            "args": ["--mode", "stdio"],
            "env": {},
        },
        "ninja-researcher": {
            "command": "ninja-researcher",
            "args": ["--mode", "stdio"],
            "env": {},
        },
        "ninja-secretary": {
            "command": "ninja-secretary",
            "args": ["--mode", "stdio"],
            "env": {},
        },
    }

    # Add API key to env if available
    if api_key:
        for server_config in servers.values():
            server_config["env"]["OPENROUTER_API_KEY"] = api_key

    # Determine which servers to install
    if args.all or (not args.coder and not args.researcher and not args.secretary):
        servers_to_install = list(servers.keys())
    else:
        servers_to_install = []
        if args.coder:
            servers_to_install.append("ninja-coder")
        if args.researcher:
            servers_to_install.append("ninja-researcher")
        if args.secretary:
            servers_to_install.append("ninja-secretary")

    # Register servers
    print()
    for server_name in servers_to_install:
        if server_name in config["mcpServers"] and not args.force:
            print_colored(f"  ⚠ {server_name} already registered (use --force to overwrite)", "yellow")
        else:
            config["mcpServers"][server_name] = servers[server_name]
            print_colored(f"  ✓ Registered {server_name}", "green")

    # Write config
    with mcp_config_path.open("w") as f:
        json.dump(config, f, indent=2)
        f.write("\n")

    print()
    print_colored(f"✓ Configuration saved to {mcp_config_path}", "green")
    print()
    print_colored("Next steps:", "bold")
    print_colored("  1. Restart Claude Code to load the new configuration", "dim")
    print_colored("  2. Run 'ninja-config doctor' to verify setup", "dim")


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
        return any(model.get("id") == model_name for model in data.get("data", []))

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

  # Diagnose issues
  ninja-config doctor
  ninja-config doctor --fix
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

    # Doctor command
    doctor_parser = subparsers.add_parser(
        "doctor",
        help="Diagnose and fix configuration issues",
    )
    doctor_parser.add_argument(
        "--fix",
        action="store_true",
        help="Auto-fix issues where possible",
    )

    # Setup Claude command
    setup_claude_parser = subparsers.add_parser(
        "setup-claude",
        help="Setup Claude Code MCP configuration",
    )
    setup_claude_parser.add_argument(
        "--coder",
        action="store_true",
        help="Register ninja-coder server",
    )
    setup_claude_parser.add_argument(
        "--researcher",
        action="store_true",
        help="Register ninja-researcher server",
    )
    setup_claude_parser.add_argument(
        "--secretary",
        action="store_true",
        help="Register ninja-secretary server",
    )
    setup_claude_parser.add_argument(
        "--all",
        action="store_true",
        help="Register all servers (default)",
    )
    setup_claude_parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing server configurations",
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
    elif args.command == "doctor":
        cmd_doctor(args)
    elif args.command == "setup-claude":
        cmd_setup_claude(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
