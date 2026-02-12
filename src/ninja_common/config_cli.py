#!/usr/bin/env python3
"""
ninja-config CLI tool for managing configuration.

Allows users to view and update Ninja MCP configuration settings
after installation.

UNIFIED ENTRY POINT: Use 'ninja-config configure' for all configuration needs.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import httpx

from ninja_common.config_manager import ConfigManager


# Import ninja_config modules if available
try:
    from ninja_config.interactive_configurator import run_power_configurator

    HAS_POWER_CONFIGURATOR = True
except ImportError:
    HAS_POWER_CONFIGURATOR = False


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
        ninja_servers = [
            "ninja-coder",
            "ninja-researcher",
            "ninja-secretary",
            "ninja-prompts",
        ]

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

    # Check operators (at least one should be installed)
    operators_found = []
    if shutil.which("aider"):
        operators_found.append("aider")
        print_colored("  ✓ aider is installed", "green")
    if shutil.which("opencode"):
        operators_found.append("opencode")
        print_colored("  ✓ opencode is installed", "green")
    if shutil.which("claude"):
        operators_found.append("claude")
        print_colored("  ✓ claude (Claude Code) is installed", "green")
    if shutil.which("gemini"):
        operators_found.append("gemini")
        print_colored("  ✓ gemini is installed", "green")

    if not operators_found:
        print_colored("  ⚠ No operators found (need at least one for ninja-coder)", "yellow")
        print_colored("    Install one of:", "dim")
        print_colored("      • Aider: uv tool install aider-chat", "dim")
        print_colored("      • OpenCode: https://opencode.dev", "dim")
        print_colored("      • Claude Code: https://claude.ai/download", "dim")
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


def cmd_configure(args: argparse.Namespace) -> None:
    """
    Run interactive configurator (MAIN ENTRY POINT).

    This is the unified configuration entry point for all ninja-mcp settings.
    Use --quick for simple API key + operator selection.
    Use --full (default) for comprehensive TUI configurator.

    Args:
        args: Command arguments.
    """
    if not HAS_POWER_CONFIGURATOR:
        print_colored("Power configurator not available.", "red")
        print_colored("Install with: pip install InquirerPy", "dim")
        return

    # Check for mode flags
    quick_mode = getattr(args, "quick", False)
    modern_mode = getattr(args, "modern", False)

    if quick_mode:
        # Quick mode: simple API key + operator selection
        print_colored("Quick Configuration Mode", "cyan")
        print_colored("─" * 40, "dim")
        _run_quick_configure(args.config)
    elif modern_mode:
        # Modern TUI mode: tree-based navigation with textual
        try:
            from ninja_config.modern_tui import run_modern_tui
            sys.exit(run_modern_tui(args.config))
        except ImportError as e:
            print_colored(f"Modern TUI not available: {e}", "red")
            print_colored("Install with: pip install textual rich", "dim")
            sys.exit(1)
        except KeyboardInterrupt:
            print("\nCancelled.")
            sys.exit(1)
    else:
        # Full mode: comprehensive TUI configurator
        try:
            sys.exit(run_power_configurator(args.config))
        except KeyboardInterrupt:
            print("\nCancelled.")
            sys.exit(1)


def _run_quick_configure(config_path: str | None = None) -> None:
    """Run quick configuration mode.

    Provides simple API key and operator selection without full TUI.

    Args:
        config_path: Optional path to config file.
    """
    import getpass

    config_mgr = ConfigManager(config_path)

    print()
    print_colored("1. API Key Configuration", "bold")
    print_colored("─" * 40, "dim")

    # Check current API key
    current_key = config_mgr.get("OPENROUTER_API_KEY")
    if current_key:
        masked = f"{current_key[:4]}...{current_key[-4:]}" if len(current_key) > 8 else "***"
        print_colored(f"Current OpenRouter API key: {masked}", "dim")

    # Ask for new key
    new_key = getpass.getpass("Enter OpenRouter API key (or press Enter to keep current): ")
    if new_key:
        config_mgr.set("OPENROUTER_API_KEY", new_key)
        print_colored("✓ API key updated", "green")
    else:
        print_colored("✓ Keeping current API key", "dim")

    print()
    print_colored("2. Operator Selection", "bold")
    print_colored("─" * 40, "dim")

    # Detect installed operators
    operators = []
    if shutil.which("opencode"):
        operators.append(("opencode", "OpenCode - Multi-provider CLI"))
    if shutil.which("aider"):
        operators.append(("aider", "Aider - OpenRouter-based CLI"))
    if shutil.which("gemini"):
        operators.append(("gemini", "Gemini CLI - Google native"))
    if shutil.which("claude"):
        operators.append(("claude", "Claude Code - Anthropic native"))

    if not operators:
        print_colored("No operators found. Install one of:", "yellow")
        print_colored("  • OpenCode: https://opencode.dev", "dim")
        print_colored("  • Aider: uv tool install aider-chat", "dim")
        print_colored("  • Claude Code: https://claude.ai/download", "dim")
        return

    print("Available operators:")
    for i, (op_id, op_desc) in enumerate(operators, 1):
        print(f"  {i}. {op_desc}")

    # Get selection
    current_op = config_mgr.get("NINJA_CODE_BIN") or "aider"
    default_idx = 1
    for i, (op_id, _) in enumerate(operators, 1):
        if op_id == current_op:
            default_idx = i
            break

    selection = input(f"Select operator [{default_idx}]: ").strip() or str(default_idx)
    try:
        idx = int(selection) - 1
        if 0 <= idx < len(operators):
            selected_op = operators[idx][0]
            config_mgr.set("NINJA_CODE_BIN", selected_op)
            print_colored(f"✓ Operator set to: {selected_op}", "green")
        else:
            print_colored("Invalid selection", "red")
    except ValueError:
        print_colored("Invalid selection", "red")

    print()
    print_colored("✓ Quick configuration complete!", "green")
    print_colored("Run 'ninja-config configure' for full options.", "dim")


def cmd_update(args: argparse.Namespace) -> None:
    """
    Update ninja-mcp to the latest version.

    Args:
        args: Command arguments.
    """
    try:
        from ninja_config.auto_updater import AutoUpdater

        print_colored("🔄 Starting ninja-mcp auto-updater...", "cyan")
        print()

        updater = AutoUpdater()
        result = updater.update()

        if result.get("verified"):
            print()
            print_colored("✅ Update completed successfully!", "green")
            print()
            print_colored("You can now use:", "dim")
            print_colored("  - ninja-config configure", "dim")
            print_colored("  - ninja-daemon status", "dim")
            print_colored("  - ninja-coder (via MCP)", "dim")
        else:
            print()
            print_colored("⚠️  Update completed but verification failed", "yellow")
            print_colored("Please check the verification results above", "dim")
            sys.exit(1)

    except ImportError:
        print_colored("❌ Auto-updater not available in this installation", "red")
        print_colored("Please update manually:", "dim")
        print_colored("  cd /path/to/ninja-cli-mcp", "dim")
        print_colored("  git pull", "dim")
        print_colored("  uv tool install --reinstall --force .", "dim")
        print_colored("  ninja-daemon restart", "dim")
        sys.exit(1)
    except Exception as e:
        print_colored(f"❌ Update failed: {e}", "red")
        print_colored("Please update manually:", "dim")
        print_colored("  cd /path/to/ninja-cli-mcp", "dim")
        print_colored("  git pull", "dim")
        print_colored("  uv tool install --reinstall --force .", "dim")
        print_colored("  ninja-daemon restart", "dim")
        sys.exit(1)


def cmd_setup_claude(args: argparse.Namespace) -> None:
    """
    Setup Claude Code MCP configuration using 'claude mcp add' command.

    Args:
        args: Command arguments.
    """
    import shutil
    import subprocess

    print_colored("Setting up Claude Code MCP configuration...", "cyan")
    print()

    # Check if claude CLI is available
    if not shutil.which("claude"):
        print_colored("  ✗ Claude Code CLI not found", "red")
        print_colored("  Install from: https://claude.ai/download", "dim")
        return

    # Define servers to register
    servers = [
        "ninja-coder",
        "ninja-researcher",
        "ninja-secretary",
        "ninja-prompts",
    ]

    # Determine which servers to install
    if args.all or (
        not args.coder
        and not args.researcher
        and not args.secretary
        and not args.prompts
    ):
        servers_to_install = servers
    else:
        servers_to_install = []
        if args.coder:
            servers_to_install.append("ninja-coder")
        if args.researcher:
            servers_to_install.append("ninja-researcher")
        if args.secretary:
            servers_to_install.append("ninja-secretary")
        if args.prompts:
            servers_to_install.append("ninja-prompts")

    # Register servers using claude mcp add
    print()
    for server_name in servers_to_install:
        # Remove existing entry if --force
        if args.force:
            subprocess.run(
                ["claude", "mcp", "remove", server_name, "-s", "user"],
                check=False,
                capture_output=True,
            )

        # Add server
        result = subprocess.run(
            [
                "claude",
                "mcp",
                "add",
                "--scope",
                "user",
                "--transport",
                "stdio",
                server_name,
                "--",
                server_name,
            ],
            check=False,
            capture_output=True,
            text=True,
        )

        if result.returncode == 0:
            print_colored(f"  ✓ Registered {server_name}", "green")
        elif "already exists" in result.stderr:
            print_colored(
                f"  ⚠ {server_name} already registered (use --force to overwrite)", "yellow"
            )
        else:
            print_colored(f"  ✗ Failed to register {server_name}: {result.stderr.strip()}", "red")

    print()
    print_colored("✓ Configuration complete", "green")
    print()
    print_colored("Verify with: claude mcp list", "dim")


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
  # Full interactive configuration (RECOMMENDED)
  ninja-config configure

  # Quick setup (API key + operator only)
  ninja-config configure --quick

  # Update to the latest version
  ninja-config update

  # List all configuration
  ninja-config list

  # Get a specific value
  ninja-config get NINJA_CODER_MODEL

  # Set a value
  ninja-config set NINJA_CODER_MODEL anthropic/claude-sonnet-4

  # Diagnose issues
  ninja-config doctor
  ninja-config doctor --fix

  # Setup Claude Code MCP servers
  ninja-config setup-claude
        """,
    )

    parser.add_argument(
        "--config",
        help="Path to config file (default: ~/.ninja-mcp.env)",
        default=None,
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # Configure command (MAIN ENTRY POINT)
    configure_parser = subparsers.add_parser(
        "configure",
        help="Interactive configuration manager (MAIN ENTRY POINT)",
    )
    configure_parser.add_argument(
        "--quick",
        action="store_true",
        help="Quick setup mode (API key + operator only)",
    )
    configure_parser.add_argument(
        "--full",
        action="store_true",
        help="Full TUI configurator (default)",
    )
    configure_parser.add_argument(
        "--modern",
        action="store_true",
        help="Modern TUI with tree navigation (EXPERIMENTAL)",
    )

    # List command
    subparsers.add_parser("list", help="List all configuration values")

    # Show config (alias for list)
    subparsers.add_parser(
        "show",
        help="Show current configuration (alias for list)",
    )

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
        "--prompts",
        action="store_true",
        help="Register ninja-prompts server",
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

    # Update command
    subparsers.add_parser(
        "update",
        help="Update ninja-mcp to the latest version",
    )

    args = parser.parse_args()

    # Print header for all commands except get
    if args.command != "get":
        print()
        print_header()

    # Dispatch to command handler using dictionary mapping
    command_handlers = {
        "configure": cmd_configure,
        "list": cmd_list,
        "show": cmd_list,  # Alias for list
        "get": cmd_get,
        "set": cmd_set,
        "doctor": cmd_doctor,
        "setup-claude": cmd_setup_claude,
        "update": cmd_update,
    }

    if args.command in command_handlers:
        command_handlers[args.command](args)
    # Default to configure if no command given
    elif args.command is None:
        args.quick = False
        cmd_configure(args)
    else:
        print_colored(f"Unknown command: {args.command}", "red")
        print_colored("Run 'ninja-config configure' for interactive configuration.", "dim")
        parser.print_help()


if __name__ == "__main__":
    main()
