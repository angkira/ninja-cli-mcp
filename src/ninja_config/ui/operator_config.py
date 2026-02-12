"""Operator and provider configuration UI.

This module handles operator selection, provider configuration, API key management,
and OpenCode authentication flows.
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

from ninja_common.config_manager import ConfigManager
from ninja_config.model_selector import (
    OPENCODE_PROVIDERS,
    check_provider_auth,
    configure_opencode_provider,
)
from ninja_config.ui.base import check_opencode_auth, detect_installed_tools, get_masked_value


def manage_api_keys(config_manager: ConfigManager, config: dict[str, str]) -> None:
    """Manage API keys interactively.

    Args:
        config_manager: Configuration manager instance
        config: Current configuration dictionary
    """
    print("\n" + "=" * 80)
    print("  🔑 API KEY MANAGEMENT")
    print("=" * 80)

    api_keys = [
        (
            "OPENROUTER_API_KEY",
            "OpenRouter",
            "https://openrouter.ai/keys",
            "For Aider and general AI access",
        ),
        (
            "ANTHROPIC_API_KEY",
            "Anthropic",
            "https://console.anthropic.com/settings/keys",
            "For Claude models",
        ),
        ("OPENAI_API_KEY", "OpenAI", "https://platform.openai.com/api-keys", "For GPT models"),
        (
            "GOOGLE_API_KEY",
            "Google",
            "https://aistudio.google.com/app/apikey",
            "For Gemini models",
        ),
        (
            "PERPLEXITY_API_KEY",
            "Perplexity",
            "https://www.perplexity.ai/settings/api",
            "For research quality",
        ),
        ("SERPER_API_KEY", "Serper", "https://serper.dev", "For Google search integration"),
        (
            "ZHIPU_API_KEY",
            "Zhipu AI (Z.ai)",
            "https://open.bigmodel.cn/usercenter/apikeys",
            "For GLM models via z.ai",
        ),
    ]

    # Show current status
    print("\n📋 Current API Keys:")
    for key, name, _, _ in api_keys:
        current = config.get(key, "")
        status = "✓ Set" if current else "✗ Not set"
        masked = get_masked_value(current) if current else "Not set"
        print(f"  {name:15} {status:10} {masked}")

    # Select key to manage
    choices = [
        Choice(
            value=(key, name, url, desc),
            name=f"{name:15} • {desc:35} [{get_masked_value(config.get(key, ''))}]",
        )
        for key, name, url, desc in api_keys
    ]
    choices.append(Separator())
    choices.append(Choice(value=None, name="← Back"))

    selected = inquirer.select(
        message="Select API key to manage:",
        choices=choices,
        pointer="►",
    ).execute()

    if not selected:
        return

    key, name, url, desc = selected

    print(f"\n🔐 {name} API Key")
    print(f"   Get your key from: {url}")
    print(f"   Purpose: {desc}")

    current_value = config.get(key, "")
    if current_value:
        print(f"\nCurrent value: {get_masked_value(current_value)}")

    action = inquirer.select(
        message="What would you like to do?",
        choices=[
            Choice("update", name="Update API key"),
            Choice("remove", name="Remove API key"),
            Choice("back", name="← Back"),
        ],
        pointer="►",
    ).execute()

    if action == "update":
        new_value = inquirer.secret(
            message=f"Enter new {name} API key:",
        ).execute()

        if new_value:
            config_manager.set(key, new_value)
            config[key] = new_value
            print(f"\n✅ {name} API key updated successfully")
        else:
            print("\n💡  No changes made")

    elif action == "remove":
        confirm = inquirer.confirm(
            message=f"⚠️  Remove {name} API key?",
            default=False,
        ).execute()

        if confirm:
            if key in config:
                del config[key]
                # Remove from config file
                config_file = config_manager.config_file
                if config_file.exists():
                    lines = []
                    with open(config_file) as f:
                        for line in f:
                            if not line.startswith(f"{key}="):
                                lines.append(line)
                    with open(config_file, "w") as f:
                        f.writelines(lines)
                print(f"\n✅ {name} API key removed")
            else:
                print(f"\n💡  {name} API key was not set")
        else:
            print("\n💡  No changes made")


def configure_operators(config_manager: ConfigManager, config: dict[str, str]) -> None:
    """Configure operator settings with provider selection flow.

    Args:
        config_manager: Configuration manager instance
        config: Current configuration dictionary
    """
    print("\n" + "=" * 80)
    print("  🎯 OPERATOR CONFIGURATION")
    print("=" * 80)

    # Detect installed operators
    tools = detect_installed_tools()

    # Operator descriptions with provider info
    operator_info = {
        "aider": ("Aider", "OpenRouter-based CLI", ["openrouter"]),
        "opencode": (
            "OpenCode",
            "Multi-provider CLI (75+ LLMs)",
            ["anthropic", "google", "openai", "github", "openrouter"],
        ),
        "gemini": ("Gemini CLI", "Google native CLI", ["google"]),
        "claude": ("Claude Code", "Anthropic's official CLI", ["anthropic"]),
        "cursor": ("Cursor", "AI code editor", ["openai", "anthropic"]),
    }

    if not tools:
        print("\n⚠️  No operators detected!")
        print("   Install at least one operator:")
        print("     • Aider: uv tool install aider-chat")
        print("     • OpenCode: https://opencode.dev/download")
        print("     • Claude Code: https://claude.ai/download")
        print("     • Gemini CLI: npm install -g @google/generative-ai-cli")
        return

    # Show current operator
    current_operator = config.get("NINJA_CODE_BIN", "Not set")
    print(f"\n📋 Current operator: {current_operator}")

    # Build choices with provider info
    choices = []
    for name, path in tools.items():
        info = operator_info.get(name, (name.title(), "Unknown", []))
        display_name, desc, providers = info
        provider_str = ", ".join(providers) if providers else "unknown"
        choices.append(Choice(name, name=f"{display_name:15} • {desc:30} [Providers: {provider_str}]"))

    choices.append(Separator())
    choices.append(Choice(None, name="<- Back"))

    selected = inquirer.select(
        message="Select operator:",
        choices=choices,
        pointer="►",
    ).execute()

    if not selected:
        return

    config_manager.set("NINJA_CODE_BIN", selected)
    config["NINJA_CODE_BIN"] = selected
    print(f"\n✅ Operator set to: {selected}")

    # If OpenCode selected, ask for provider selection
    if selected == "opencode":
        select_opencode_provider(config_manager, config)
    elif selected == "claude":
        print("\n💡 Run 'claude auth' to authenticate with Anthropic")
    elif selected == "aider":
        print("\n💡 Set OPENROUTER_API_KEY in 'API Key Management'")

    # Clear model selection when changing operator
    model_keys = [
        k
        for k in config
        if "MODEL" in k
        and k != "NINJA_MODEL_QUICK"
        and k != "NINJA_MODEL_SEQUENTIAL"
        and k != "NINJA_MODEL_PARALLEL"
    ]
    for model_key in model_keys:
        if model_key in config:
            del config[model_key]
            # Remove from config file
            config_file = config_manager.config_file
            if config_file.exists():
                lines = []
                with open(config_file) as f:
                    for line in f:
                        if not line.startswith(f"{model_key}="):
                            lines.append(line)
                with open(config_file, "w") as f:
                    f.writelines(lines)

    print("\n💡  Module model selections cleared (task-based models preserved)")
    print("   Go to 'Model Selection' or 'Coder Setup' to choose models")


def select_opencode_provider(config_manager: ConfigManager, config: dict[str, str]) -> str | None:
    """Select provider for OpenCode operator.

    Args:
        config_manager: Configuration manager instance
        config: Current configuration dictionary

    Returns:
        Selected provider ID, or None if cancelled
    """
    print("\n" + "-" * 50)
    print("  📡 PROVIDER SELECTION (OpenCode)")
    print("-" * 50)

    # Check authentication status for each provider
    auth_status = {}
    for provider_id, _, _ in OPENCODE_PROVIDERS:
        auth_status[provider_id] = check_provider_auth(provider_id)

    # Build choices
    choices = []
    for provider_id, display_name, desc in OPENCODE_PROVIDERS:
        is_auth = auth_status.get(provider_id, False)
        auth_symbol = "✓" if is_auth else "✗"
        choices.append(
            Choice(
                provider_id,
                name=f"{auth_symbol} {display_name:20} • {desc}",
            )
        )

    choices.append(Separator())
    choices.append(Choice(None, name="<- Skip provider selection"))

    selected_provider = inquirer.select(
        message="Select provider:",
        choices=choices,
        pointer="►",
    ).execute()

    if not selected_provider:
        return None

    # Check if provider needs authentication
    is_authenticated = auth_status.get(selected_provider, False)

    if not is_authenticated:
        # Find provider display name
        provider_display = selected_provider.title()
        for pid, name, _ in OPENCODE_PROVIDERS:
            if pid == selected_provider:
                provider_display = name
                break

        print(f"\n⚠️  {provider_display} is not authenticated")

        # API key URLs for each provider
        api_key_urls = {
            "anthropic": "https://console.anthropic.com/settings/keys",
            "google": "https://aistudio.google.com/app/apikey",
            "openai": "https://platform.openai.com/api-keys",
            "openrouter": "https://openrouter.ai/keys",
            "github-copilot": "https://github.com/settings/copilot",
        }

        api_key_url = api_key_urls.get(selected_provider, "")
        if api_key_url:
            print(f"   Get your API key from: {api_key_url}")

        setup_now = inquirer.confirm(
            message="Set up authentication now?",
            default=True,
        ).execute()

        if setup_now:
            api_key = inquirer.secret(
                message=f"Enter {provider_display} API key:",
            ).execute()

            if api_key:
                # Save credentials using model_selector function
                success = configure_opencode_provider(selected_provider, api_key)
                if success:
                    print(f"\n✅ {provider_display} credentials saved")
                    # Also save to ninja config for backup
                    api_key_name = f"{selected_provider.upper().replace('-', '_')}_API_KEY"
                    config_manager.set(api_key_name, api_key)
                    config[api_key_name] = api_key
                else:
                    print(f"\n❌ Failed to configure {provider_display}")
                    return None
            else:
                print("\n💡 No API key provided, skipping authentication")

    # Save selected provider
    config_manager.set("NINJA_CODER_PROVIDER", selected_provider)
    config["NINJA_CODER_PROVIDER"] = selected_provider
    print(f"\n✅ Provider set to: {selected_provider}")

    return selected_provider


def configure_opencode_auth(config_manager: ConfigManager, config: dict[str, str]) -> None:
    """Configure OpenCode authentication with z.ai support.

    Args:
        config_manager: Configuration manager instance
        config: Current configuration dictionary
    """
    print("\n" + "=" * 80)
    print("  🌐 OPENCODE AUTHENTICATION")
    print("=" * 80)

    import shutil
    if not shutil.which("opencode"):
        print("\n⚠️  OpenCode CLI not found")
        print("   Install from: https://opencode.dev/download")
        return

    # Check current auth status
    print("\n📊 Current Authentication Status:")
    authenticated_providers = check_opencode_auth()

    providers = [
        ("anthropic", "Anthropic/Claude", "opencode auth anthropic"),
        ("google", "Google/Gemini", "opencode auth google"),
        ("openai", "OpenAI/GPT", "opencode auth openai"),
        ("github", "GitHub Copilot", "opencode auth github"),
        ("zai", "Z.ai / Zhipu AI", "opencode auth zai"),
    ]

    for provider, name, _ in providers:
        status = "✓ Authenticated" if provider in authenticated_providers else "✗ Not authenticated"
        print(f"   {name:20} {status}")

    # Select provider to authenticate
    choices = [
        Choice(
            value=(provider, name, cmd),
            name=f"{name:25} • {'✓ Authenticated' if provider in authenticated_providers else '✗ Not authenticated'}",
        )
        for provider, name, cmd in providers
    ]
    choices.append(Separator())
    choices.append(Choice(value=None, name="← Back"))

    selected = inquirer.select(
        message="Select provider to authenticate:",
        choices=choices,
        pointer="►",
    ).execute()

    if not selected:
        return

    provider, name, cmd = selected

    print(f"\n🔄 Authenticating with {name}...")
    print("   Follow the prompts to complete authentication...\n")

    try:
        subprocess.run(cmd.split(), check=False)
        print(f"\n✅ {name} authentication completed")
        print("   Run this command again to verify status")
    except Exception as e:
        print(f"\n❌ Authentication failed: {e}")
