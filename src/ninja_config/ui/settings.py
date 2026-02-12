"""Settings and advanced configuration UI components.

This module provides functions for configuring search, daemon, IDE integration,
and advanced settings.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from InquirerPy import inquirer
from InquirerPy.base.control import Choice
from InquirerPy.separator import Separator

from ninja_config.ui.base import get_masked_value


def configure_search(config_manager, config: dict) -> None:
    """Configure search provider with Perplexity model selection.

    Args:
        config_manager: ConfigManager instance for saving settings.
        config: Current configuration dictionary.
    """
    print("\n" + "=" * 80)
    print("  🔍 SEARCH PROVIDER CONFIGURATION")
    print("=" * 80)

    current_provider = config.get("NINJA_SEARCH_PROVIDER", "duckduckgo")
    current_model = config.get("NINJA_RESEARCHER_MODEL", "sonar")
    print(f"\n📋 Current provider: {current_provider}")
    if current_provider == "perplexity":
        print(f"📋 Current model: {current_model}")

    choices = [
        Choice("duckduckgo", name="DuckDuckGo  •  Free, no API key needed"),
        Choice("serper", name="Serper/Google  •  Good quality, needs API key"),
        Choice("perplexity", name="Perplexity AI  •  Best quality, needs API key"),
    ]

    selected = inquirer.select(
        message="Select search provider:",
        choices=choices,
        pointer="►",
        default=current_provider,
    ).execute()

    if selected:
        config_manager.set("NINJA_SEARCH_PROVIDER", selected)
        print(f"\n✅ Search provider set to: {selected}")

        # Check if API key needed
        if selected == "perplexity":
            if not config.get("PERPLEXITY_API_KEY"):
                print("\n⚠️  Perplexity API key required")
                print("   Go to 'API Key Management' to add it")
            else:
                # Offer Perplexity model selection
                configure_perplexity_model(config_manager, config)
        elif selected == "serper" and not config.get("SERPER_API_KEY"):
            print("\n⚠️  Serper API key required")
            print("   Go to 'API Key Management' to add it")


def configure_perplexity_model(config_manager, config: dict) -> None:
    """Configure Perplexity model for researcher.

    Args:
        config_manager: ConfigManager instance for saving settings.
        config: Current configuration dictionary.
    """
    print("\n" + "-" * 50)
    print("  📊 PERPLEXITY MODEL SELECTION")
    print("-" * 50)

    # NOTE: Perplexity models are hardcoded here since Perplexity API doesn't support
    # dynamic model discovery. These are the official Perplexity Sonar models.
    perplexity_models = [
        ("sonar", "Sonar", "Fast search-focused model"),
        ("sonar-pro", "Sonar Pro", "Advanced search with better reasoning"),
        ("sonar-reasoning", "Sonar Reasoning", "Complex reasoning with search"),
    ]

    current_model = config.get("NINJA_RESEARCHER_MODEL", "sonar")
    print(f"\nCurrent model: {current_model}")

    choices = [
        Choice(value=model_id, name=f"{name:20} • {desc}")
        for model_id, name, desc in perplexity_models
    ]
    choices.append(Separator())
    choices.append(Choice(value=None, name="← Keep current"))

    selected = inquirer.select(
        message="Select Perplexity model:",
        choices=choices,
        pointer="►",
        default=current_model,
    ).execute()

    if selected:
        config_manager.set("NINJA_RESEARCHER_MODEL", selected)
        print(f"\n✅ Researcher model set to: {selected}")


def configure_daemon(config_manager, config: dict) -> None:
    """Configure daemon settings.

    Args:
        config_manager: ConfigManager instance for saving settings.
        config: Current configuration dictionary.
    """
    print("\n" + "=" * 80)
    print("  ⚙️  DAEMON CONFIGURATION")
    print("=" * 80)

    # Show current daemon status
    daemon_enabled = config.get("NINJA_ENABLE_DAEMON", "true").lower() == "true"
    print("\n📊 Current Status:")
    print(f"   Daemon Enabled: {'✓ Yes' if daemon_enabled else '✗ No'}")

    daemon_ports = {
        "NINJA_CODER_PORT": 8100,
        "NINJA_RESEARCHER_PORT": 8101,
        "NINJA_SECRETARY_PORT": 8102,
        "NINJA_RESOURCES_PORT": 8106,
        "NINJA_PROMPTS_PORT": 8107,
    }

    print("\n🔌 Ports:")
    for key, default_port in daemon_ports.items():
        current_port = config.get(key, str(default_port))
        print(f"   {key.split('_')[1].title():12} {current_port}")

    # Enable/disable daemon
    enable_daemon = inquirer.confirm(
        message="Enable daemon mode? (recommended for better performance)",
        default=daemon_enabled,
    ).execute()

    if enable_daemon != daemon_enabled:
        config_manager.set("NINJA_ENABLE_DAEMON", str(enable_daemon).lower())
        status = "enabled" if enable_daemon else "disabled"
        print(f"\n✅ Daemon {status}")

    # Configure ports
    print("\n🔌 Port Configuration:")
    for key, default_port in daemon_ports.items():
        current_port = int(config.get(key, str(default_port)))
        module_name = key.split("_")[1].title()

        new_port = inquirer.number(
            message=f"{module_name} port:",
            default=current_port,
            min_allowed=1024,
            max_allowed=65535,
        ).execute()

        if new_port and new_port != current_port:
            config_manager.set(key, str(new_port))
            print(f"   ✅ {module_name} port updated to: {new_port}")


def configure_ide(config_manager, config: dict) -> None:
    """Configure IDE integration.

    Args:
        config_manager: ConfigManager instance for saving settings.
        config: Current configuration dictionary.
    """
    print("\n" + "=" * 80)
    print("  🖥️  IDE INTEGRATION")
    print("=" * 80)

    # Check for IDE configs
    ide_configs = {}
    claude_config = Path.home() / ".claude.json"
    if claude_config.exists():
        ide_configs["claude"] = str(claude_config)

    vscode_configs = [
        Path.home() / ".config" / "Code" / "User" / "settings.json",
        Path.home() / "Library" / "Application Support" / "Code" / "User" / "settings.json",
    ]
    for config_path in vscode_configs:
        if config_path.exists():
            ide_configs["vscode"] = str(config_path)
            break

    zed_config = Path.home() / ".config" / "zed" / "settings.json"
    if zed_config.exists():
        ide_configs["zed"] = str(zed_config)

    print("\n📋 Detected IDE Configurations:")
    if ide_configs:
        for ide, config_path in ide_configs.items():
            print(f"   ✓ {ide.title():10} {config_path}")
    else:
        print("   No IDE configurations detected")

    # Setup options
    choices = [
        Choice("claude", name="Claude Code  •  Automatic MCP server registration"),
        Choice("vscode", name="VS Code  •  Manual configuration required"),
        Choice("zed", name="Zed  •  Manual configuration required"),
        Choice("opencode", name="OpenCode  •  MCP server registration"),
        Separator(),
        Choice(None, name="← Back"),
    ]

    selected = inquirer.select(
        message="Select IDE to configure:",
        choices=choices,
        pointer="►",
    ).execute()

    if not selected:
        return

    if selected == "claude":
        setup_claude_integration()
    elif selected == "opencode":
        setup_opencode_integration()
    else:
        print(f"\n💡  {selected.title()} configuration requires manual setup")
        print("   Refer to documentation for detailed instructions")


def setup_claude_integration() -> None:
    """Setup Claude Code integration."""
    if not shutil.which("claude"):
        print("\n⚠️  Claude Code CLI not found")
        print("   Install from: https://claude.ai/download")
        return

    print("\n🔄 Setting up Claude Code MCP configuration...")

    # Register all servers
    servers = [
        "ninja-coder",
        "ninja-researcher",
        "ninja-secretary",
        "ninja-prompts",
    ]

    success_count = 0
    for server_name in servers:
        # Remove existing entry first
        subprocess.run(
            ["claude", "mcp", "remove", server_name, "-s", "user"],
            capture_output=True,
            check=False,
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
            capture_output=True,
            text=True,
            check=False,
        )

        if result.returncode == 0:
            print(f"   ✓ Registered {server_name}")
            success_count += 1
        else:
            print(f"   ✗ Failed to register {server_name}")

    if success_count == len(servers):
        print("\n✅ Claude Code integration completed successfully")
    else:
        print(f"\n⚠️  Claude Code integration completed with {success_count}/{len(servers)} servers")


def setup_opencode_integration() -> None:
    """Setup OpenCode integration."""
    if not shutil.which("opencode"):
        print("\n⚠️  OpenCode CLI not found")
        print("   Install from: https://opencode.dev/download")
        return

    print("\n🔄 Setting up OpenCode MCP configuration...")
    print("   Run 'ninja-config configure' → 'OpenCode Authentication' to manage providers")


def advanced_settings(config_manager, config: dict) -> None:
    """Manage advanced settings.

    Args:
        config_manager: ConfigManager instance for saving settings.
        config: Current configuration dictionary.
    """
    print("\n" + "=" * 80)
    print("  🔧 ADVANCED SETTINGS")
    print("=" * 80)

    # Show all settings
    if not config:
        print("\n⚠️  No configuration found")
        return

    print("\n📋 All Configuration Settings:")
    sorted_config = sorted(config.items())

    # Paginate if too many settings
    page_size = 20
    page = 0
    total_pages = (len(sorted_config) + page_size - 1) // page_size

    while True:
        start_idx = page * page_size
        end_idx = min(start_idx + page_size, len(sorted_config))
        page_items = sorted_config[start_idx:end_idx]

        print(f"\n📄 Page {page + 1}/{total_pages}:")
        for key, value in page_items:
            if "API_KEY" in key or "KEY" in key:
                display_value = get_masked_value(value)
            else:
                display_value = value if value else "*** NOT SET ***"
            print(f"  {key:35} {display_value}")

        if total_pages > 1:
            nav_choices = []
            if page > 0:
                nav_choices.append(Choice("prev", name="← Previous Page"))
            if page < total_pages - 1:
                nav_choices.append(Choice("next", name="Next Page →"))
            nav_choices.append(Choice("edit", name="✏️  Edit Setting"))
            nav_choices.append(Choice("back", name="← Back"))

            action = inquirer.select(
                message="Navigation:",
                choices=nav_choices,
                pointer="►",
            ).execute()

            if action == "prev":
                page -= 1
            elif action == "next":
                page += 1
            elif action == "edit":
                edit_setting(config_manager, config)
                break
            else:
                break
        else:
            # No pagination needed
            action = inquirer.select(
                message="What would you like to do?",
                choices=[
                    Choice("edit", name="✏️  Edit Setting"),
                    Choice("back", name="← Back"),
                ],
                pointer="►",
            ).execute()

            if action == "edit":
                edit_setting(config_manager, config)
            break


def edit_setting(config_manager, config: dict) -> None:
    """Edit a specific setting.

    Args:
        config_manager: ConfigManager instance for saving settings.
        config: Current configuration dictionary.
    """
    # Get all keys
    keys = sorted(config.keys())

    if not keys:
        print("\n⚠️  No settings to edit")
        return

    # Select key to edit
    choices = [
        Choice(key, name=f"{key:35} [{config.get(key, '*** NOT SET ***')}]") for key in keys
    ]
    choices.append(Separator())
    choices.append(Choice(None, name="← Back"))

    selected_key = inquirer.select(
        message="Select setting to edit:",
        choices=choices,
        pointer="►",
    ).execute()

    if not selected_key:
        return

    current_value = config.get(selected_key, "")
    new_value = inquirer.text(
        message=f"Enter new value for {selected_key}:",
        default=current_value,
    ).execute()

    if new_value != current_value:
        config_manager.set(selected_key, new_value)
        print(f"\n✅ {selected_key} updated")
    else:
        print("\n💡  No changes made")


def reset_configuration(config_manager, config: dict) -> None:
    """Reset all configuration.

    Args:
        config_manager: ConfigManager instance for saving settings.
        config: Current configuration dictionary.
    """
    print("\n" + "=" * 80)
    print("  🗑️  RESET CONFIGURATION")
    print("=" * 80)

    confirm = inquirer.confirm(
        message="⚠️  This will delete ALL configuration. Are you sure?",
        default=False,
    ).execute()

    if confirm:
        # Clear config in memory
        config.clear()

        # Remove config file
        config_file = config_manager.config_file
        if config_file.exists():
            config_file.unlink()

        print("\n✅ Configuration reset successfully")
        print("   Run 'ninja-config configure' to set up again")
    else:
        print("\n💡  Reset cancelled")
