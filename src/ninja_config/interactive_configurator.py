"""
Powerful interactive configurator for Ninja MCP with TUI interface.
"""

import getpass
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    import InquirerPy.inquirer as inquirer
    from InquirerPy.base.control import Choice
    from InquirerPy.separator import Separator
    from InquirerPy.validator import PathValidator

    HAS_INQUIRERPY = True
except ImportError:
    try:
        from InquirerPy import inquirer
        from InquirerPy.base.control import Choice
        from InquirerPy.separator import Separator
        from InquirerPy.validator import PathValidator

        HAS_INQUIRERPY = True
    except ImportError:
        HAS_INQUIRERPY = False
        print("⚠️  InquirerPy not installed. Install with: pip install InquirerPy")
        sys.exit(1)

from ninja_common.config_manager import ConfigManager


class PowerConfigurator:
    """Powerful interactive configurator for Ninja MCP."""

    def __init__(self, config_path: Optional[str] = None):
        """Initialize configurator."""
        self.config_manager = ConfigManager(config_path)
        self.config = self._load_current_config()

    def _load_current_config(self) -> Dict[str, str]:
        """Load current configuration."""
        return self.config_manager.list_all()

    def _save_config(self, key: str, value: str) -> None:
        """Save configuration value."""
        self.config_manager.set(key, value)
        self.config[key] = value

    def _get_masked_value(self, value: str) -> str:
        """Return masked version of sensitive value."""
        if not value or len(value) < 8:
            return "*** NOT SET ***"
        return f"{value[:4]}...{value[-4:]}"

    def _detect_installed_tools(self) -> Dict[str, str]:
        """Detect installed AI coding tools."""
        tools = {}

        # Check for aider
        if shutil.which("aider"):
            tools["aider"] = shutil.which("aider")

        # Check for opencode
        if shutil.which("opencode"):
            tools["opencode"] = shutil.which("opencode")

        # Check for gemini
        if shutil.which("gemini"):
            tools["gemini"] = shutil.which("gemini")

        # Check for claude (Claude Code)
        if shutil.which("claude"):
            tools["claude"] = shutil.which("claude")

        # Check for cursor
        if shutil.which("cursor"):
            tools["cursor"] = shutil.which("cursor")

        return tools

    def _check_opencode_auth(self) -> List[str]:
        """Check OpenCode authentication status."""
        if not shutil.which("opencode"):
            return []

        try:
            result = subprocess.run(
                ["opencode", "auth", "list"], capture_output=True, text=True, check=False, timeout=5
            )
            if result.returncode == 0:
                # Parse output to find authenticated providers
                providers = []
                output = result.stdout.lower()
                if "anthropic" in output:
                    providers.append("anthropic")
                if "google" in output or "gemini" in output:
                    providers.append("google")
                if "openai" in output:
                    providers.append("openai")
                if "github" in output:
                    providers.append("github")
                if "zai" in output or "zhipu" in output:
                    providers.append("zai")
                return providers
        except Exception:
            pass

        return []

    def run(self) -> None:
        """Run the main interactive configurator."""
        if not HAS_INQUIRERPY:
            print("❌ InquirerPy required for interactive mode")
            return

        self._show_welcome()

        while True:
            try:
                action = self._show_main_menu()
                if not action or action == "exit":
                    break

                if action == "overview":
                    self._show_configuration_overview()
                elif action == "api_keys":
                    self._manage_api_keys()
                elif action == "operators":
                    self._configure_operators()
                elif action == "models":
                    self._configure_models()
                elif action == "task_models":
                    self._configure_task_based_models()
                elif action == "search":
                    self._configure_search()
                elif action == "daemon":
                    self._configure_daemon()
                elif action == "ide":
                    self._configure_ide()
                elif action == "opencode_auth":
                    self._configure_opencode_auth()
                elif action == "advanced":
                    self._advanced_settings()
                elif action == "reset":
                    self._reset_configuration()

            except KeyboardInterrupt:
                print("\n\n👋 Goodbye!")
                break
            except Exception as e:
                print(f"\n❌ Error: {e}")
                input("\nPress Enter to continue...")

    def _show_welcome(self) -> None:
        """Show welcome message."""
        print("\n" + "🌟" * 80)
        print("  🌟 NINJA MCP POWER CONFIGURATOR 🌟")
        print("  The ultimate configuration experience for Ninja MCP")
        print("🌟" * 80)

    def _show_main_menu(self) -> str:
        """Show main configuration menu."""
        print("\n" + "=" * 80)
        print("  🎛️  MAIN CONFIGURATION MENU")
        print("=" * 80)

        # Show current status
        api_key_status = (
            "✓ Configured"
            if any("API_KEY" in k and v for k, v in self.config.items())
            else "⚠️  Not set"
        )
        operator_status = self.config.get("NINJA_CODE_BIN", "Not set")
        model_status = self.config.get("NINJA_CODER_MODEL", "Not set")
        quick_model = self.config.get("NINJA_MODEL_QUICK", "Not set")
        sequential_model = self.config.get("NINJA_MODEL_SEQUENTIAL", "Not set")

        print(f"\n📋 Current Status:")
        print(f"   🔑 API Keys:     {api_key_status}")
        print(f"   🎯 Operator:     {operator_status}")
        print(f"   🤖 Coder Model:  {model_status}")
        print(f"   ⚡ Quick Model:  {quick_model}")
        print(f"   📊 Sequential:   {sequential_model}")
        print(f"   🔍 Search:       {self.config.get('NINJA_SEARCH_PROVIDER', 'duckduckgo')}")

        choices = [
            Choice(
                value="overview", name="📋 Configuration Overview  •  See all settings at a glance"
            ),
            Separator(),
            Choice(value="api_keys", name="🔑 API Key Management  •  Add/update all service keys"),
            Choice(
                value="operators",
                name="🎯 Operator Configuration  •  Choose your AI coding assistant",
            ),
            Choice(value="models", name="🤖 Model Selection  •  Set models for each module"),
            Choice(value="task_models", name="📊 Task-Based Models  •  Configure models for different task types"),
            Choice(value="search", name="🔍 Search Provider  •  Configure web search capabilities"),
            Choice(
                value="daemon", name="⚙️  Daemon Settings  •  Performance and port configuration"
            ),
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

    def _show_configuration_overview(self) -> None:
        """Show comprehensive configuration overview."""
        print("\n" + "=" * 80)
        print("  📋 CONFIGURATION OVERVIEW")
        print("=" * 80)

        if not self.config:
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

        for key, value in sorted(self.config.items()):
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
                        display_value = self._get_masked_value(value)
                    else:
                        display_value = value if value else "*** NOT SET ***"
                    print(f"  {key:35} {display_value}")

        print(f"\n📁 Configuration file: {self.config_manager.config_file}")

        # Show system status
        print(f"\n📊 System Status:")
        tools = self._detect_installed_tools()
        if tools:
            print(f"  🛠️  Installed Tools: {', '.join(tools.keys())}")
        else:
            print(f"  🛠️  Installed Tools: None detected")

        # Check daemon status
        try:
            result = subprocess.run(
                ["ninja-daemon", "status"], capture_output=True, text=True, check=False, timeout=3
            )
            if result.returncode == 0:
                print(f"  🚀 Daemon Status: Running")
            else:
                print(f"  🚀 Daemon Status: Stopped")
        except FileNotFoundError:
            print(f"  🚀 Daemon Status: Not installed")
        except Exception:
            print(f"  🚀 Daemon Status: Unknown")

    def _manage_api_keys(self) -> None:
        """Manage API keys interactively."""
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
            current = self.config.get(key, "")
            status = "✓ Set" if current else "✗ Not set"
            masked = self._get_masked_value(current) if current else "Not set"
            print(f"  {name:15} {status:10} {masked}")

        # Select key to manage
        choices = [
            Choice(
                value=(key, name, url, desc),
                name=f"{name:15} • {desc:35} [{self._get_masked_value(self.config.get(key, ''))}]",
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

        current_value = self.config.get(key, "")
        if current_value:
            print(f"\nCurrent value: {self._get_masked_value(current_value)}")

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
                self._save_config(key, new_value)
                print(f"\n✅ {name} API key updated successfully")
            else:
                print("\nℹ️  No changes made")

        elif action == "remove":
            confirm = inquirer.confirm(
                message=f"⚠️  Remove {name} API key?",
                default=False,
            ).execute()

            if confirm:
                if key in self.config:
                    del self.config[key]
                    # Remove from config file
                    config_file = self.config_manager.config_file
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
                    print(f"\nℹ️  {name} API key was not set")
            else:
                print("\nℹ️  No changes made")

    def _configure_operators(self) -> None:
        """Configure operator settings with provider-first flow."""
        print("\n" + "=" * 80)
        print("  🎯 OPERATOR CONFIGURATION")
        print("=" * 80)

        # Detect installed operators
        tools = self._detect_installed_tools()

        # Operator descriptions with provider info
        operator_info = {
            "aider": ("Aider", "OpenRouter-based CLI", ["openrouter"]),
            "opencode": ("OpenCode", "Multi-provider CLI (75+ LLMs)", ["anthropic", "google", "openai", "github", "zai"]),
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
        current_operator = self.config.get("NINJA_CODE_BIN", "Not set")
        print(f"\n📋 Current operator: {current_operator}")

        # Build choices with provider info
        choices = []
        for name, path in tools.items():
            status = "✓ Current" if name == current_operator else "Available"
            info = operator_info.get(name, (name.title(), "Unknown", []))
            display_name, desc, providers = info
            provider_str = ", ".join(providers) if providers else "unknown"
            choices.append(Choice(name, name=f"{display_name:15} • {desc:30} [Providers: {provider_str}]"))

        choices.append(Separator())
        choices.append(Choice(None, name="← Back"))

        selected = inquirer.select(
            message="Select operator:",
            choices=choices,
            pointer="►",
        ).execute()

        if selected:
            self._save_config("NINJA_CODE_BIN", selected)
            print(f"\n✅ Operator set to: {selected}")

            # Show available providers for selected operator
            info = operator_info.get(selected, (selected.title(), "Unknown", []))
            _, _, providers = info
            if providers:
                print(f"\n📋 Available providers for {selected}:")
                for provider in providers:
                    print(f"   • {provider}")

            # Prompt for authentication if needed
            if selected == "opencode":
                print("\n💡 Go to 'OpenCode Authentication' to authenticate with providers")
            elif selected == "claude":
                print("\n💡 Run 'claude auth' to authenticate with Anthropic")
            elif selected == "aider":
                print("\n💡 Set OPENROUTER_API_KEY in 'API Key Management'")

            # Clear model selection when changing operator
            model_keys = [k for k in self.config.keys() if "MODEL" in k and k != "NINJA_MODEL_QUICK" and k != "NINJA_MODEL_SEQUENTIAL" and k != "NINJA_MODEL_PARALLEL"]
            for model_key in model_keys:
                if model_key in self.config:
                    del self.config[model_key]
                    # Remove from config file
                    config_file = self.config_manager.config_file
                    if config_file.exists():
                        lines = []
                        with open(config_file) as f:
                            for line in f:
                                if not line.startswith(f"{model_key}="):
                                    lines.append(line)
                        with open(config_file, "w") as f:
                            f.writelines(lines)

            print(
                "\nℹ️  Module model selections cleared (task-based models preserved)"
            )
            print("   Go to 'Model Selection' to choose new models for modules")

    def _configure_models(self) -> None:
        """Configure models for each module."""
        print("\n" + "=" * 80)
        print("  🤖 MODEL CONFIGURATION")
        print("=" * 80)

        modules = [
            ("coder", "AI Code Assistant"),
            ("researcher", "Web Research Engine"),
            ("secretary", "Documentation & Analysis"),
            ("resources", "Resource Templates"),
            ("prompts", "Prompt Management"),
        ]

        # Show current models
        print("\n📋 Current Models:")
        for module, desc in modules:
            key = f"NINJA_{module.upper()}_MODEL"
            current = self.config.get(key, "Not set")
            print(f"  {desc:25} {current}")

        # Select module to configure
        choices = [
            Choice(
                value=(module, desc),
                name=f"{desc:25} [{self.config.get(f'NINJA_{module.upper()}_MODEL', 'Not set')}]",
            )
            for module, desc in modules
        ]
        choices.append(Separator())
        choices.append(Choice(value=None, name="← Back"))

        selected = inquirer.select(
            message="Select module to configure:",
            choices=choices,
            pointer="►",
        ).execute()

        if not selected:
            return

        module, desc = selected
        key = f"NINJA_{module.upper()}_MODEL"

        print(f"\n🎯 {desc} Model Configuration")

        # Get model name
        current_model = self.config.get(key, "")
        model = inquirer.text(
            message="Enter model name (or leave empty to keep current):",
            default=current_model,
            instruction="e.g., anthropic/claude-sonnet-4, openai/gpt-4o, google/gemini-2.0-flash-exp",
        ).execute()

        if model:
            self._save_config(key, model)
            print(f"\n✅ {desc} model updated to: {model}")
        elif model == "":
            print("\nℹ️  No changes made")

    def _configure_task_based_models(self) -> None:
        """Configure task-based model selection."""
        print("\n" + "=" * 80)
        print("  📊 TASK-BASED MODEL SELECTION")
        print("=" * 80)

        # Show current task models
        task_models = [
            ("NINJA_MODEL_QUICK", "Quick Tasks", "Fast simple tasks", "anthropic/claude-haiku-4.5"),
            ("NINJA_MODEL_SEQUENTIAL", "Sequential Tasks", "Complex multi-step tasks", "anthropic/claude-sonnet-4"),
            ("NINJA_MODEL_PARALLEL", "Parallel Tasks", "High concurrency parallel tasks", "anthropic/claude-haiku-4.5"),
        ]

        print("\n📋 Current Task Models:")
        for key, name, _, default in task_models:
            current = self.config.get(key, default)
            print(f"  {name:20} {current}")

        # Show cost/quality preferences
        prefer_cost = self.config.get("NINJA_PREFER_COST", "false").lower() == "true"
        prefer_quality = self.config.get("NINJA_PREFER_QUALITY", "false").lower() == "true"
        preference = "Cost" if prefer_cost else "Quality" if prefer_quality else "Balanced"
        print(f"\n🎯 Current Preference: {preference}")

        # Select what to configure
        choices = [
            Choice(value="quick", name="⚡ Quick Tasks Model     • Fast simple tasks (default: Claude Haiku 4.5)"),
            Choice(value="sequential", name="📊 Sequential Model     • Complex multi-step (default: Claude Sonnet 4)"),
            Choice(value="parallel", name="🔀 Parallel Model       • High concurrency (default: Claude Haiku 4.5)"),
            Separator(),
            Choice(value="preferences", name="🎯 Model Preferences    • Cost vs Quality toggle"),
            Choice(value="reset_task_models", name="🔄 Reset to Defaults    • Restore default models"),
            Separator(),
            Choice(value=None, name="← Back"),
        ]

        selected = inquirer.select(
            message="What would you like to configure?",
            choices=choices,
            pointer="►",
        ).execute()

        if not selected:
            return

        if selected == "preferences":
            self._configure_model_preferences()
        elif selected == "reset_task_models":
            self._reset_task_models(task_models)
        else:
            self._configure_single_task_model(selected, task_models)

    def _configure_single_task_model(self, task_type: str, task_models: list) -> None:
        """Configure a single task model."""
        # Find the task model config
        task_info = None
        for key, name, desc, default in task_models:
            if task_type.lower() in name.lower():
                task_info = (key, name, desc, default)
                break

        if not task_info:
            return

        key, name, desc, default = task_info
        current = self.config.get(key, default)

        print(f"\n🎯 {name} Model Configuration")
        print(f"   Purpose: {desc}")
        print(f"   Current: {current}")

        # Recommended models based on task type
        if task_type == "quick":
            recommended = [
                ("anthropic/claude-haiku-4.5", "Claude Haiku 4.5", "Fast and cost-effective (Recommended)"),
                ("claude-haiku-4", "Claude Haiku 4 (Claude Code)", "Fast via Claude Code"),
                ("glm-4.0", "GLM-4.0 (z.ai)", "Low cost, fast"),
                ("openai/gpt-4o-mini", "GPT-4o Mini", "OpenAI's fast model"),
            ]
        elif task_type == "sequential":
            recommended = [
                ("anthropic/claude-sonnet-4", "Claude Sonnet 4", "High quality (Recommended)"),
                ("claude-sonnet-4", "Claude Sonnet 4 (Claude Code)", "Via Claude Code"),
                ("glm-4.7", "GLM-4.7 (z.ai)", "Supports Coding Plan API"),
                ("anthropic/claude-opus-4", "Claude Opus 4", "Maximum quality"),
            ]
        else:  # parallel
            recommended = [
                ("anthropic/claude-haiku-4.5", "Claude Haiku 4.5", "Balanced (Recommended)"),
                ("glm-4.6v", "GLM-4.6V (z.ai)", "20 concurrent limit"),
                ("claude-haiku-4", "Claude Haiku 4 (Claude Code)", "Via Claude Code"),
                ("openai/gpt-4o-mini", "GPT-4o Mini", "OpenAI's fast model"),
            ]

        print("\n📋 Recommended Models:")
        choices = [
            Choice(value=model_id, name=f"{name:30} • {desc}")
            for model_id, name, desc in recommended
        ]
        choices.append(Separator())
        choices.append(Choice(value="custom", name="✏️  Enter custom model"))
        choices.append(Choice(value=None, name="← Keep current"))

        selected = inquirer.select(
            message=f"Select model for {name}:",
            choices=choices,
            pointer="►",
        ).execute()

        if selected == "custom":
            custom_model = inquirer.text(
                message="Enter model name:",
                default=current,
                instruction="e.g., anthropic/claude-sonnet-4, glm-4.7, openai/gpt-4o",
            ).execute()
            if custom_model:
                self._save_config(key, custom_model)
                print(f"\n✅ {name} model set to: {custom_model}")
        elif selected:
            self._save_config(key, selected)
            print(f"\n✅ {name} model set to: {selected}")

    def _configure_model_preferences(self) -> None:
        """Configure cost vs quality preferences."""
        print("\n🎯 Model Preferences")
        print("   This affects automatic model selection recommendations.")

        prefer_cost = self.config.get("NINJA_PREFER_COST", "false").lower() == "true"
        prefer_quality = self.config.get("NINJA_PREFER_QUALITY", "false").lower() == "true"

        choices = [
            Choice(value="balanced", name="⚖️  Balanced       • Balance between cost and quality (Default)"),
            Choice(value="cost", name="💰 Prefer Cost    • Use cheaper models when possible"),
            Choice(value="quality", name="🏆 Prefer Quality • Use best models for maximum quality"),
        ]

        current = "cost" if prefer_cost else "quality" if prefer_quality else "balanced"

        selected = inquirer.select(
            message="Select preference:",
            choices=choices,
            pointer="►",
            default=current,
        ).execute()

        if selected == "cost":
            self._save_config("NINJA_PREFER_COST", "true")
            self._save_config("NINJA_PREFER_QUALITY", "false")
            print("\n✅ Preference set to: Prefer Cost")
        elif selected == "quality":
            self._save_config("NINJA_PREFER_COST", "false")
            self._save_config("NINJA_PREFER_QUALITY", "true")
            print("\n✅ Preference set to: Prefer Quality")
        else:
            self._save_config("NINJA_PREFER_COST", "false")
            self._save_config("NINJA_PREFER_QUALITY", "false")
            print("\n✅ Preference set to: Balanced")

    def _reset_task_models(self, task_models: list) -> None:
        """Reset task models to defaults."""
        confirm = inquirer.confirm(
            message="Reset all task models to defaults?",
            default=False,
        ).execute()

        if confirm:
            for key, name, desc, default in task_models:
                self._save_config(key, default)
            self._save_config("NINJA_PREFER_COST", "false")
            self._save_config("NINJA_PREFER_QUALITY", "false")
            print("\n✅ Task models reset to defaults")

    def _configure_search(self) -> None:
        """Configure search provider with Perplexity model selection."""
        print("\n" + "=" * 80)
        print("  🔍 SEARCH PROVIDER CONFIGURATION")
        print("=" * 80)

        current_provider = self.config.get("NINJA_SEARCH_PROVIDER", "duckduckgo")
        current_model = self.config.get("NINJA_RESEARCHER_MODEL", "sonar")
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
            self._save_config("NINJA_SEARCH_PROVIDER", selected)
            print(f"\n✅ Search provider set to: {selected}")

            # Check if API key needed
            if selected == "perplexity":
                if not self.config.get("PERPLEXITY_API_KEY"):
                    print("\n⚠️  Perplexity API key required")
                    print("   Go to 'API Key Management' to add it")
                else:
                    # Offer Perplexity model selection
                    self._configure_perplexity_model()
            elif selected == "serper" and not self.config.get("SERPER_API_KEY"):
                print("\n⚠️  Serper API key required")
                print("   Go to 'API Key Management' to add it")

    def _configure_perplexity_model(self) -> None:
        """Configure Perplexity model for researcher."""
        print("\n" + "-" * 50)
        print("  📊 PERPLEXITY MODEL SELECTION")
        print("-" * 50)

        # Perplexity models
        perplexity_models = [
            ("sonar", "Sonar", "Fast search-focused model"),
            ("sonar-pro", "Sonar Pro", "Advanced search with better reasoning"),
            ("sonar-reasoning", "Sonar Reasoning", "Complex reasoning with search"),
        ]

        current_model = self.config.get("NINJA_RESEARCHER_MODEL", "sonar")
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
            self._save_config("NINJA_RESEARCHER_MODEL", selected)
            print(f"\n✅ Researcher model set to: {selected}")

    def _configure_daemon(self) -> None:
        """Configure daemon settings."""
        print("\n" + "=" * 80)
        print("  ⚙️  DAEMON CONFIGURATION")
        print("=" * 80)

        # Show current daemon status
        daemon_enabled = self.config.get("NINJA_ENABLE_DAEMON", "true").lower() == "true"
        print(f"\n📊 Current Status:")
        print(f"   Daemon Enabled: {'✓ Yes' if daemon_enabled else '✗ No'}")

        daemon_ports = {
            "NINJA_CODER_PORT": 8100,
            "NINJA_RESEARCHER_PORT": 8101,
            "NINJA_SECRETARY_PORT": 8102,
            "NINJA_RESOURCES_PORT": 8106,
            "NINJA_PROMPTS_PORT": 8107,
        }

        print(f"\n🔌 Ports:")
        for key, default_port in daemon_ports.items():
            current_port = self.config.get(key, str(default_port))
            print(f"   {key.split('_')[1].title():12} {current_port}")

        # Enable/disable daemon
        enable_daemon = inquirer.confirm(
            message="Enable daemon mode? (recommended for better performance)",
            default=daemon_enabled,
        ).execute()

        if enable_daemon != daemon_enabled:
            self._save_config("NINJA_ENABLE_DAEMON", str(enable_daemon).lower())
            status = "enabled" if enable_daemon else "disabled"
            print(f"\n✅ Daemon {status}")

        # Configure ports
        print(f"\n🔌 Port Configuration:")
        for key, default_port in daemon_ports.items():
            current_port = int(self.config.get(key, str(default_port)))
            module_name = key.split("_")[1].title()

            new_port = inquirer.number(
                message=f"{module_name} port:",
                default=current_port,
                min_allowed=1024,
                max_allowed=65535,
            ).execute()

            if new_port and new_port != current_port:
                self._save_config(key, str(new_port))
                print(f"   ✅ {module_name} port updated to: {new_port}")

    def _configure_ide(self) -> None:
        """Configure IDE integration."""
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

        print(f"\n📋 Detected IDE Configurations:")
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
            self._setup_claude_integration()
        elif selected == "opencode":
            self._setup_opencode_integration()
        else:
            print(f"\nℹ️  {selected.title()} configuration requires manual setup")
            print("   Refer to documentation for detailed instructions")

    def _setup_claude_integration(self) -> None:
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
            "ninja-resources",
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
            print(f"\n✅ Claude Code integration completed successfully")
        else:
            print(
                f"\n⚠️  Claude Code integration completed with {success_count}/{len(servers)} servers"
            )

    def _setup_opencode_integration(self) -> None:
        """Setup OpenCode integration."""
        if not shutil.which("opencode"):
            print("\n⚠️  OpenCode CLI not found")
            print("   Install from: https://opencode.dev/download")
            return

        print("\n🔄 Setting up OpenCode MCP configuration...")
        print("   Run 'ninja-config configure' → 'OpenCode Authentication' to manage providers")

    def _configure_opencode_auth(self) -> None:
        """Configure OpenCode authentication with z.ai support."""
        print("\n" + "=" * 80)
        print("  🌐 OPENCODE AUTHENTICATION")
        print("=" * 80)

        if not shutil.which("opencode"):
            print("\n⚠️  OpenCode CLI not found")
            print("   Install from: https://opencode.dev/download")
            return

        # Check current auth status
        print("\n📊 Current Authentication Status:")
        authenticated_providers = self._check_opencode_auth()

        providers = [
            ("anthropic", "Anthropic/Claude", "opencode auth anthropic"),
            ("google", "Google/Gemini", "opencode auth google"),
            ("openai", "OpenAI/GPT", "opencode auth openai"),
            ("github", "GitHub Copilot", "opencode auth github"),
            ("zai", "Z.ai / Zhipu AI", "opencode auth zai"),
        ]

        for provider, name, _ in providers:
            status = (
                "✓ Authenticated" if provider in authenticated_providers else "✗ Not authenticated"
            )
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

    def _advanced_settings(self) -> None:
        """Manage advanced settings."""
        print("\n" + "=" * 80)
        print("  🔧 ADVANCED SETTINGS")
        print("=" * 80)

        # Show all settings
        if not self.config:
            print("\n⚠️  No configuration found")
            return

        print("\n📋 All Configuration Settings:")
        sorted_config = sorted(self.config.items())

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
                    display_value = self._get_masked_value(value)
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
                    self._edit_setting()
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
                    self._edit_setting()
                break

    def _edit_setting(self) -> None:
        """Edit a specific setting."""
        # Get all keys
        keys = sorted(self.config.keys())

        if not keys:
            print("\n⚠️  No settings to edit")
            return

        # Select key to edit
        choices = [
            Choice(key, name=f"{key:35} [{self.config.get(key, '*** NOT SET ***')}]")
            for key in keys
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

        current_value = self.config.get(selected_key, "")
        new_value = inquirer.text(
            message=f"Enter new value for {selected_key}:",
            default=current_value,
        ).execute()

        if new_value != current_value:
            self._save_config(selected_key, new_value)
            print(f"\n✅ {selected_key} updated")
        else:
            print("\nℹ️  No changes made")

    def _reset_configuration(self) -> None:
        """Reset all configuration."""
        print("\n" + "=" * 80)
        print("  🗑️  RESET CONFIGURATION")
        print("=" * 80)

        confirm = inquirer.confirm(
            message="⚠️  This will delete ALL configuration. Are you sure?",
            default=False,
        ).execute()

        if confirm:
            # Clear config in memory
            self.config.clear()

            # Remove config file
            config_file = self.config_manager.config_file
            if config_file.exists():
                config_file.unlink()

            print("\n✅ Configuration reset successfully")
            print("   Run 'ninja-config configure' to set up again")
        else:
            print("\nℹ️  Reset cancelled")


def run_power_configurator(config_path: Optional[str] = None) -> int:
    """Run the power configurator."""
    try:
        configurator = PowerConfigurator(config_path)
        configurator.run()
        return 0
    except KeyboardInterrupt:
        print("\n\n👋 Configuration session ended")
        return 0
    except Exception as e:
        print(f"\n❌ Configuration error: {e}")
        return 1


if __name__ == "__main__":
    config_path = sys.argv[1] if len(sys.argv) > 1 else None
    sys.exit(run_power_configurator(config_path))
