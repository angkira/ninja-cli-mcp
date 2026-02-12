"""Main configuration menu and overview display.

This module handles the main menu interface and configuration overview display.
All functions are stateless and accept configuration as parameters.
"""

import subprocess
from pathlib import Path


try:
    from InquirerPy import inquirer
    from InquirerPy.base.control import Choice
    from InquirerPy.separator import Separator

    HAS_INQUIRERPY = True
except ImportError:
    HAS_INQUIRERPY = False

from ninja_config.ui.base import detect_installed_tools, get_masked_value


def show_welcome() -> None:
    """Show welcome message."""
    print("\n" + "🌟" * 80)
    print("  🌟 NINJA MCP POWER CONFIGURATOR 🌟")
    print("  The ultimate configuration experience for Ninja MCP")
    print("🌟" * 80)


def show_main_menu(config: dict[str, str]) -> str:
    """Show main configuration menu and return selected action.

    Args:
        config: Current configuration dictionary

    Returns:
        Selected action string (e.g., 'coder_setup', 'exit', 'overview')
    """
    print("\n" + "=" * 80)
    print("  🎛️  MAIN CONFIGURATION MENU")
    print("=" * 80)

    # Show current status
    api_key_status = (
        "✓ Configured"
        if any("API_KEY" in k and v for k, v in config.items())
        else "⚠️  Not set"
    )
    operator_status = config.get("NINJA_CODE_BIN", "Not set")
    model_status = config.get("NINJA_CODER_MODEL", "Not set")
    quick_model = config.get("NINJA_MODEL_QUICK", "Not set")
    sequential_model = config.get("NINJA_MODEL_SEQUENTIAL", "Not set")

    print("\n📋 Current Status:")
    print(f"   🔑 API Keys:     {api_key_status}")
    print(f"   🎯 Operator:     {operator_status}")
    print(f"   🤖 Coder Model:  {model_status}")
    print(f"   ⚡ Quick Model:  {quick_model}")
    print(f"   📊 Sequential:   {sequential_model}")
    print(f"   🔍 Search:       {config.get('NINJA_SEARCH_PROVIDER', 'duckduckgo')}")

    choices = [
        Choice(value="overview", name="📋 Configuration Overview  •  See all settings at a glance"),
        Separator(),
        Choice(
            value="coder_setup",
            name="🎯 Coder Setup  •  Operator + Provider + Models flow",
        ),
        Choice(
            value="secretary_setup",
            name="📋 Secretary Setup  •  Configure secretary module",
        ),
        Separator(),
        Choice(value="api_keys", name="🔑 API Key Management  •  Add/update all service keys"),
        Choice(
            value="operators",
            name="🎯 Operator Configuration  •  Choose your AI coding assistant",
        ),
        Choice(value="models", name="🤖 Model Selection  •  Set models for each module"),
        Choice(
            value="task_models",
            name="📊 Task-Based Models  •  Configure models for different task types",
        ),
        Choice(value="search", name="🔍 Search Provider  •  Configure web search capabilities"),
        Choice(value="daemon", name="⚙️  Daemon Settings  •  Performance and port configuration"),
        Choice(value="ide", name="🖥️  IDE Integration  •  Connect to editors and IDEs"),
        Separator(),
        Choice(
            value="opencode_auth",
            name="🌐 OpenCode Authentication  •  Manage provider credentials",
        ),
        Choice(
            value="advanced",
            name="🔧 Advanced Settings  •  Fine-tune all configuration options",
        ),
        Separator(),
        Choice(value="reset", name="🗑️  Reset Configuration  •  Clear all settings"),
        Choice(value="exit", name="🚪 Exit"),
    ]

    result = inquirer.select(
        message="What would you like to configure?",
        choices=choices,
        pointer="►",
        instruction="Use arrow keys to navigate, Enter to select",
    ).execute()

    return result


def show_configuration_overview(config: dict[str, str], config_file: Path) -> None:
    """Show comprehensive configuration overview.

    Args:
        config: Current configuration dictionary
        config_file: Path to the configuration file
    """
    print("\n" + "=" * 80)
    print("  📋 CONFIGURATION OVERVIEW")
    print("=" * 80)

    if not config:
        print("\n⚠️  No configuration found")
        return

    # Group configuration by category
    categories = {
        "🔑 API Keys": {},
        "🎯 Operators": {},
        "🤖 Models": {},
        "🔍 Search": {},
        "⚙️  Daemon": {},
        "🖥️  IDE": {},
        "🔧 Advanced": {},
    }

    for key, value in sorted(config.items()):
        if "API_KEY" in key:
            categories["🔑 API Keys"][key] = value
        elif key.startswith("NINJA_CODE"):
            categories["🎯 Operators"][key] = value
        elif "MODEL" in key:
            categories["🤖 Models"][key] = value
        elif "SEARCH" in key:
            categories["🔍 Search"][key] = value
        elif "PORT" in key or "DAEMON" in key:
            categories["⚙️  Daemon"][key] = value
        elif "IDE" in key:
            categories["🖥️  IDE"][key] = value
        else:
            categories["🔧 Advanced"][key] = value

    # Display categories
    for category, items in categories.items():
        if items:
            print(f"\n{category}:")
            for key, value in sorted(items.items()):
                if "API_KEY" in key or "KEY" in key:
                    display_value = get_masked_value(value)
                else:
                    display_value = value if value else "*** NOT SET ***"
                print(f"  {key:35} {display_value}")

    print(f"\n📁 Configuration file: {config_file}")

    # Show system status
    print("\n📊 System Status:")
    tools = detect_installed_tools()
    if tools:
        print(f"  🛠️  Installed Tools: {', '.join(tools.keys())}")
    else:
        print("  🛠️  Installed Tools: None detected")

    # Check daemon status
    try:
        result = subprocess.run(
            ["ninja-daemon", "status"],
            capture_output=True,
            text=True,
            check=False,
            timeout=3,
        )
        if result.returncode == 0:
            print("  🚀 Daemon Status: Running")
        else:
            print("  🚀 Daemon Status: Stopped")
    except FileNotFoundError:
        print("  🚀 Daemon Status: Not installed")
    except Exception:
        print("  🚀 Daemon Status: Unknown")
