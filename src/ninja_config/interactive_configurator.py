"""
Powerful interactive configurator for Ninja MCP with TUI interface.
"""

import shutil
import subprocess
import sys


try:
    from InquirerPy import inquirer
    from InquirerPy.base.control import Choice
    from InquirerPy.separator import Separator

    HAS_INQUIRERPY = True
except ImportError:
    try:
        from InquirerPy import inquirer
        from InquirerPy.base.control import Choice
        from InquirerPy.separator import Separator

        HAS_INQUIRERPY = True
    except ImportError:
        HAS_INQUIRERPY = False
        print("Warning: InquirerPy not installed. Install with: pip install InquirerPy")
        sys.exit(1)

from ninja_common.config_manager import ConfigManager
from ninja_common.defaults import OPENROUTER_MODELS, PERPLEXITY_MODELS, ZAI_MODELS
from ninja_config.config_shared import (
    API_KEYS,
    DAEMON_CONFIG,
    OPERATOR_MAP,
    PROVIDER_KEY_URLS,
    TASK_MODEL_DEFAULTS,
    detect_ides,
    detect_tools,
    get_fallback_models,
    mask_key,
    register_claude_mcp,
)
from ninja_config.litellm import (
    LITELLM_PROVIDER_ID,
    is_litellm_configured,
    read_litellm_config,
    write_litellm_config,
)
from ninja_config.model_selector import (
    OPENCODE_PROVIDERS,
    check_provider_auth,
    configure_opencode_provider,
    get_provider_models,
)


class PowerConfigurator:
    """Powerful interactive configurator for Ninja MCP."""

    def __init__(self, config_path: str | None = None):
        """Initialize configurator."""
        self.config_manager = ConfigManager(config_path)
        self.config = self._load_current_config()

    def _load_current_config(self) -> dict[str, str]:
        """Load current configuration."""
        return self.config_manager.list_all()

    def _save_config(self, key: str, value: str) -> None:
        """Save configuration value."""
        self.config_manager.set(key, value)
        self.config[key] = value

    def _get_masked_value(self, value: str) -> str:
        return mask_key(value)

    def _detect_installed_tools(self) -> dict[str, str]:
        return detect_tools()

    def _check_opencode_auth(self) -> list[str]:
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
                if "opencode go" in output:
                    providers.append("opencode-go")
                if "coding plan" in output or "zai-coding-plan" in output:
                    providers.append("zai-coding-plan")
                if "openrouter" in output:
                    providers.append("openrouter")
                if "opencode" in output:
                    providers.append("opencode")
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
                elif action == "coder_setup":
                    self._coder_setup_flow()
                elif action == "secretary_setup":
                    self._configure_secretary()
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

        print("\n📋 Current Status:")
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
        print("\n📊 System Status:")
        tools = self._detect_installed_tools()
        if tools:
            print(f"  🛠️  Installed Tools: {', '.join(tools.keys())}")
        else:
            print("  🛠️  Installed Tools: None detected")

        # Check daemon status
        try:
            result = subprocess.run(
                ["ninja-mcp", "daemon", "status"],
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

    def _manage_api_keys(self) -> None:
        """Manage API keys interactively."""
        print("\n" + "=" * 80)
        print("  🔑 API KEY MANAGEMENT")
        print("=" * 80)

        api_keys = [(k.env_var, k.display_name, k.url, k.description) for k in API_KEYS]

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
                print("\n💡  No changes made")

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
                    print(f"\n💡  {name} API key was not set")
            else:
                print("\n💡  No changes made")

    def _configure_operators(self) -> None:
        """Configure operator settings with provider selection flow."""
        print("\n" + "=" * 80)
        print("  🎯 OPERATOR CONFIGURATION")
        print("=" * 80)

        # Detect installed operators
        tools = self._detect_installed_tools()

        # Operator descriptions with provider info
        operator_info = {
            op_id: (op.display_name, op.description, list(op.providers))
            for op_id, op in OPERATOR_MAP.items()
        }

        if not tools:
            print("\n⚠️  No operators detected!")
            print("   Install at least one operator:")
            print("     • Aider: pipx install aider-chat")
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
            info = operator_info.get(name, (name.title(), "Unknown", []))
            display_name, desc, providers = info
            provider_str = ", ".join(providers) if providers else "unknown"
            choices.append(
                Choice(name, name=f"{display_name:15} • {desc:30} [Providers: {provider_str}]")
            )

        choices.append(Separator())
        choices.append(Choice(None, name="<- Back"))

        selected = inquirer.select(
            message="Select operator:",
            choices=choices,
            pointer="►",
        ).execute()

        if not selected:
            return

        self._save_config("NINJA_CODE_BIN", selected)
        print(f"\n✅ Operator set to: {selected}")

        # If OpenCode selected, ask for provider selection
        if selected == "opencode":
            self._select_opencode_provider()
        elif selected == "claude":
            print("\n💡 Run 'claude auth' to authenticate with Anthropic")
        elif selected == "aider":
            print("\n💡 Set OPENROUTER_API_KEY in 'API Key Management'")

        # Clear model selection when changing operator
        model_keys = [
            k
            for k in self.config
            if "MODEL" in k
            and k != "NINJA_MODEL_QUICK"
            and k != "NINJA_MODEL_SEQUENTIAL"
            and k != "NINJA_MODEL_PARALLEL"
        ]
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

        print("\n💡  Module model selections cleared (task-based models preserved)")
        print("   Go to 'Model Selection' or 'Coder Setup' to choose models")

    def _select_opencode_provider(self) -> str | None:
        """Select provider for OpenCode operator."""
        print("\n" + "-" * 50)
        print("  📡 PROVIDER SELECTION (OpenCode)")
        print("-" * 50)

        # OPENCODE_PROVIDERS is a list of tuples: (provider_id, display_name, description)
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

        # LiteLLM is a self-hosted proxy: configure base URL + API key + models
        # in opencode.json instead of the standard auth.json credentials flow.
        if selected_provider == LITELLM_PROVIDER_ID:
            self._configure_litellm_provider()
            return selected_provider

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
            api_key_urls = PROVIDER_KEY_URLS

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
                        self._save_config(api_key_name, api_key)
                    else:
                        print(f"\n❌ Failed to configure {provider_display}")
                        return None
                else:
                    print("\n💡 No API key provided, skipping authentication")

        # Save selected provider
        self._save_config("NINJA_CODER_PROVIDER", selected_provider)
        print(f"\n✅ Provider set to: {selected_provider}")

        return selected_provider

    def _configure_litellm_provider(self) -> None:
        """Configure a self-hosted LiteLLM proxy.

        Prompts for the proxy base URL, API key and served model ids, then
        writes the ``provider.litellm`` block into the global opencode.json.
        """
        print("\n" + "-" * 50)
        print("  🚀 LITELLM CONFIGURATION")
        print("-" * 50)
        print("\n  LiteLLM is a self-hosted OpenAI-compatible proxy.")
        print("  Point opencode at your proxy and list the models it serves.")

        current = read_litellm_config()
        if current and current["base_url"]:
            print(f"\n  Current: {current['base_url']}")
            print(f"  Models:  {', '.join(current['models']) or 'none'}")
            reconfigure = inquirer.confirm(
                message="Reconfigure LiteLLM?",
                default=True,
            ).execute()
            if not reconfigure:
                print("\n💡 Keeping current LiteLLM config")
                return
        elif is_litellm_configured():
            print("\n  LiteLLM is configured (base URL set).")

        base_url = inquirer.text(
            message="LiteLLM base URL (e.g. http://localhost:4000/v1):",
            default=(current or {}).get("base_url", ""),
        ).execute()

        if not base_url:
            print("\n💡 No base URL provided, skipping")
            return

        api_key = inquirer.secret(
            message="LiteLLM API key (master or virtual key):",
            default=(current or {}).get("api_key", ""),
        ).execute()

        models_input = inquirer.text(
            message="Served model ids (comma-separated, e.g. gpt-4o, deepseek-chat):",
            default=", ".join((current or {}).get("models", [])),
        ).execute()
        models = [m.strip() for m in models_input.split(",") if m.strip()]

        success = write_litellm_config(base_url, api_key, models)
        if success:
            print("\n✅ LiteLLM provider configured in opencode.json")
            print(f"   Base URL: {base_url}")
            print(f"   Models:   {', '.join(models) or 'none'}")
            if models:
                print("\n   Example model ids for ninja-config:")
                for m in models:
                    print(f"     litellm/{m}")
            self._save_config("NINJA_CODER_PROVIDER", LITELLM_PROVIDER_ID)
        else:
            print("\n❌ Failed to write LiteLLM config")

    def _coder_setup_flow(self) -> None:
        """Complete coder setup flow: operator -> provider -> models."""
        print("\n" + "=" * 80)
        print("  🎯 CODER SETUP")
        print("=" * 80)
        print("\n  This wizard will guide you through:")
        print("    1. Operator selection (OpenCode, Aider, Claude Code, Gemini CLI)")
        print("    2. Provider selection (for OpenCode)")
        print("    3. Model configuration (regular, quick, heavy tasks)")

        # Step 1: Operator Selection
        print("\n" + "-" * 50)
        print("  STEP 1: OPERATOR SELECTION")
        print("-" * 50)

        tools = self._detect_installed_tools()

        operator_info = {
            op_id: (op.display_name, op.description)
            for op_id, op in OPERATOR_MAP.items()
            if op_id != "cursor"
        }

        if not tools:
            print("\n⚠️  No operators detected!")
            print("   Install at least one operator:")
            print("     • OpenCode: https://opencode.dev/download")
            print("     • Aider: pipx install aider-chat")
            print("     • Claude Code: https://claude.ai/download")
            print("     • Gemini CLI: npm install -g @google/generative-ai-cli")
            return

        current_operator = self.config.get("NINJA_CODE_BIN", "Not set")
        print(f"\n📋 Current operator: {current_operator}")

        choices = []
        for name, path in tools.items():
            info = operator_info.get(name, (name.title(), "Unknown"))
            display_name, desc = info
            choices.append(Choice(name, name=f"{display_name:15} • {desc}"))

        choices.append(Separator())
        choices.append(Choice(None, name="<- Cancel setup"))

        selected_operator = inquirer.select(
            message="Select operator:",
            choices=choices,
            pointer="►",
        ).execute()

        if not selected_operator:
            print("\n💡 Setup cancelled")
            return

        self._save_config("NINJA_CODE_BIN", selected_operator)
        print(f"\n✅ Operator set to: {selected_operator}")

        # Step 2: Provider Selection (for OpenCode)
        selected_provider = None
        if selected_operator == "opencode":
            selected_provider = self._select_opencode_provider()
            if not selected_provider:
                print("\n💡 No provider selected, using default")
        elif selected_operator == "claude":
            selected_provider = "anthropic"
            self._save_config("NINJA_CODER_PROVIDER", "anthropic")
        elif selected_operator == "aider":
            selected_provider = "openrouter"
            self._save_config("NINJA_CODER_PROVIDER", "openrouter")
        elif selected_operator == "gemini":
            selected_provider = "google"
            self._save_config("NINJA_CODER_PROVIDER", "google")

        # Step 3: Model Configuration
        self._configure_coder_models(selected_operator, selected_provider)

        print("\n" + "=" * 80)
        print("  ✅ CODER SETUP COMPLETE")
        print("=" * 80)
        print(f"\n   Operator:  {selected_operator}")
        print(f"   Provider:  {selected_provider or 'default'}")
        print(f"   Model:     {self.config.get('NINJA_CODER_MODEL', 'Not set')}")
        print(f"   Quick:     {self.config.get('NINJA_MODEL_QUICK', 'Same as regular')}")
        print(f"   Heavy:     {self.config.get('NINJA_MODEL_SEQUENTIAL', 'Not set')}")

    def _configure_coder_models(
        self, operator: str | None = None, provider: str | None = None
    ) -> None:
        """Configure coder models: regular, quick, and heavy task models."""
        print("\n" + "-" * 50)
        print("  STEP 3: MODEL CONFIGURATION")
        print("-" * 50)

        # Get operator and provider if not provided
        if not operator:
            operator = self.config.get("NINJA_CODE_BIN", "opencode")
        if not provider:
            provider = self.config.get("NINJA_CODER_PROVIDER", "anthropic")

        # Fetch available models from the operator/provider
        print(f"\n🔄 Loading models from {operator}/{provider}...")

        try:
            models = get_provider_models(operator, provider)
        except Exception as e:
            print(f"\n⚠️  Failed to load models: {e}")
            print("   Using fallback model list")
            models = self._get_fallback_models(provider)

        if not models:
            print("\n⚠️  No models available, using fallback list")
            models = self._get_fallback_models(provider)

        print(f"   Found {len(models)} models\n")

        # Group models by provider with separators
        model_choices = self._build_model_choices(models, provider)

        # 3a: Regular model (NINJA_CODER_MODEL)
        print("\n📦 Regular Model (NINJA_CODER_MODEL)")
        print("   Main model for standard coding tasks")

        current_model = self.config.get("NINJA_CODER_MODEL", "")

        regular_choices = model_choices.copy()
        regular_choices.append(Separator())
        regular_choices.append(Choice("__custom__", name="📝 Enter custom model name"))
        regular_choices.append(Choice(None, name="<- Skip"))

        selected_model = inquirer.select(
            message="Select regular model:",
            choices=regular_choices,
            pointer="►",
        ).execute()

        if selected_model == "__custom__":
            selected_model = inquirer.text(
                message="Enter custom model name:",
                default=current_model,
                instruction="e.g., anthropic/claude-sonnet-4, openai/gpt-4o",
            ).execute()

        if selected_model:
            self._save_config("NINJA_CODER_MODEL", selected_model)
            print(f"   ✅ Regular model: {selected_model}")
        else:
            selected_model = current_model

        # 3b: Quick task model (NINJA_MODEL_QUICK)
        print("\n⚡ Quick Task Model (NINJA_MODEL_QUICK)")
        print("   For simple, fast tasks")

        use_same_as_regular = inquirer.confirm(
            message="Use same model as regular for quick tasks?",
            default=True,
        ).execute()

        if use_same_as_regular:
            if selected_model:
                self._save_config("NINJA_MODEL_QUICK", selected_model)
                print(f"   ✅ Quick model: {selected_model} (same as regular)")
        else:
            quick_choices = model_choices.copy()
            quick_choices.append(Separator())
            quick_choices.append(Choice("__custom__", name="📝 Enter custom model name"))
            quick_choices.append(Choice(None, name="<- Skip"))

            quick_model = inquirer.select(
                message="Select quick task model:",
                choices=quick_choices,
                pointer="►",
            ).execute()

            if quick_model == "__custom__":
                quick_model = inquirer.text(
                    message="Enter custom model name:",
                    instruction="e.g., anthropic/claude-haiku-4.5, openai/gpt-4o-mini",
                ).execute()

            if quick_model:
                self._save_config("NINJA_MODEL_QUICK", quick_model)
                print(f"   ✅ Quick model: {quick_model}")

        # 3c: Heavy task model (NINJA_MODEL_SEQUENTIAL)
        print("\n📊 Heavy Task Model (NINJA_MODEL_SEQUENTIAL)")
        print("   For complex multi-step tasks")

        heavy_choices = model_choices.copy()
        heavy_choices.append(Separator())
        heavy_choices.append(Choice("__custom__", name="📝 Enter custom model name"))
        heavy_choices.append(Choice(None, name="<- Skip"))

        heavy_model = inquirer.select(
            message="Select heavy task model:",
            choices=heavy_choices,
            pointer="►",
        ).execute()

        if heavy_model == "__custom__":
            heavy_model = inquirer.text(
                message="Enter custom model name:",
                instruction="e.g., anthropic/claude-opus-4, openai/o1",
            ).execute()

        if heavy_model:
            self._save_config("NINJA_MODEL_SEQUENTIAL", heavy_model)
            print(f"   ✅ Heavy model: {heavy_model}")

    def _build_model_choices(self, models: list, current_provider: str | None = None) -> list:
        """Build model choices grouped by provider with separators."""
        # Group models by provider
        by_provider = {}
        for model in models:
            # Handle Model dataclass objects (from get_provider_models)
            if hasattr(model, "id") and hasattr(model, "name"):
                model_id = model.id
                model_name = model.name
                model_desc = model.description if hasattr(model, "description") else ""
                provider = model.provider if hasattr(model, "provider") else ""
            # Handle dict format
            elif isinstance(model, dict):
                model_id = model.get("id", "")
                model_name = model.get("name", model_id)
                model_desc = model.get("description", "")
                provider = model.get("provider", "")
            # Handle tuple format (model_id, model_name, model_desc)
            elif isinstance(model, tuple):
                model_id, model_name, model_desc = model[:3]
                provider = (
                    model_id.split("/")[0] if "/" in model_id else current_provider or "unknown"
                )
            else:
                continue

            if not provider:
                provider = (
                    model_id.split("/")[0] if "/" in model_id else current_provider or "unknown"
                )

            if provider not in by_provider:
                by_provider[provider] = []
            by_provider[provider].append((model_id, model_name, model_desc))

        # Build choices with separators
        choices = []

        # Put current provider first if specified
        provider_order = sorted(by_provider.keys())
        if current_provider and current_provider in provider_order:
            provider_order.remove(current_provider)
            provider_order.insert(0, current_provider)

        for provider in provider_order:
            models_list = by_provider[provider]
            provider_display = provider.upper() if provider else "OTHER"
            choices.append(Separator(f"── {provider_display} ({len(models_list)} models) ──"))

            for model_id, model_name, model_desc in models_list:
                display = f"{model_name}"
                if model_desc:
                    display += f"  •  {model_desc}"

                # Add :free variant indicator for OpenRouter
                if "openrouter" in provider.lower() or "/" in model_id:
                    if ":free" in model_id:
                        display += " [FREE]"

                choices.append(Choice(model_id, name=display))

        return choices

    def _get_fallback_models(self, provider: str | None = None) -> list:
        return get_fallback_models(provider)

    def _configure_secretary(self) -> None:
        """Configure secretary module with its own operator and model."""
        print("\n" + "=" * 80)
        print("  📋 SECRETARY SETUP")
        print("=" * 80)
        print("\n  Secretary module handles documentation and analysis tasks.")
        print("  It can use a different operator/model than the coder module.")

        # Current secretary config
        current_operator = self.config.get("NINJA_SECRETARY_OPERATOR", "")
        current_model = self.config.get("NINJA_SECRETARY_MODEL", "")
        coder_operator = self.config.get("NINJA_CODE_BIN", "opencode")
        coder_model = self.config.get("NINJA_CODER_MODEL", "")

        print("\n📋 Current Configuration:")
        print(f"   Coder Operator:     {coder_operator}")
        print(f"   Coder Model:        {coder_model or 'Not set'}")
        print(f"   Secretary Operator: {current_operator or 'Same as coder'}")
        print(f"   Secretary Model:    {current_model or 'Not set'}")

        # Ask if secretary should use same operator as coder
        use_same_operator = inquirer.confirm(
            message="Use same operator as coder for secretary?",
            default=True,
        ).execute()

        if use_same_operator:
            secretary_operator = coder_operator
            self._save_config("NINJA_SECRETARY_OPERATOR", coder_operator)
            print(f"\n✅ Secretary operator: {coder_operator} (same as coder)")
        else:
            # Select different operator for secretary
            tools = self._detect_installed_tools()
            operator_info = {
                op_id: (op.display_name, op.description)
                for op_id, op in OPERATOR_MAP.items()
                if op_id != "cursor"
            }

            choices = []
            for name, path in tools.items():
                info = operator_info.get(name, (name.title(), "Unknown"))
                display_name, desc = info
                choices.append(Choice(name, name=f"{display_name:15} • {desc}"))

            choices.append(Separator())
            choices.append(Choice(None, name="<- Keep current"))

            secretary_operator = inquirer.select(
                message="Select secretary operator:",
                choices=choices,
                pointer="►",
            ).execute()

            if secretary_operator:
                self._save_config("NINJA_SECRETARY_OPERATOR", secretary_operator)
                print(f"\n✅ Secretary operator: {secretary_operator}")
            else:
                secretary_operator = current_operator or coder_operator

        # Get provider for secretary operator
        secretary_provider = None
        if secretary_operator == "opencode":
            secretary_provider = self.config.get("NINJA_CODER_PROVIDER", "anthropic")
        elif secretary_operator == "claude":
            secretary_provider = "anthropic"
        elif secretary_operator == "aider":
            secretary_provider = "openrouter"
        elif secretary_operator == "gemini":
            secretary_provider = "google"

        # Select secretary model
        print("\n" + "-" * 50)
        print("  SECRETARY MODEL SELECTION")
        print("-" * 50)

        # Ask if secretary should use same model as coder
        use_same_model = inquirer.confirm(
            message="Use same model as coder for secretary?",
            default=False,
        ).execute()

        if use_same_model and coder_model:
            self._save_config("NINJA_SECRETARY_MODEL", coder_model)
            print(f"\n✅ Secretary model: {coder_model} (same as coder)")
        else:
            # Fetch available models
            print(f"\n🔄 Loading models from {secretary_operator}/{secretary_provider}...")

            try:
                models = get_provider_models(secretary_operator, secretary_provider)
            except Exception as e:
                print(f"\n⚠️  Failed to load models: {e}")
                models = self._get_fallback_models(secretary_provider)

            if not models:
                models = self._get_fallback_models(secretary_provider)

            print(f"   Found {len(models)} models\n")

            model_choices = self._build_model_choices(models, secretary_provider)
            model_choices.append(Separator())
            model_choices.append(Choice("__custom__", name="📝 Enter custom model name"))
            model_choices.append(Choice(None, name="<- Skip"))

            secretary_model = inquirer.select(
                message="Select secretary model:",
                choices=model_choices,
                pointer="►",
            ).execute()

            if secretary_model == "__custom__":
                secretary_model = inquirer.text(
                    message="Enter custom model name:",
                    default=current_model,
                    instruction="e.g., anthropic/claude-haiku-4.5",
                ).execute()

            if secretary_model:
                self._save_config("NINJA_SECRETARY_MODEL", secretary_model)
                print(f"\n✅ Secretary model: {secretary_model}")

        print("\n" + "=" * 80)
        print("  ✅ SECRETARY SETUP COMPLETE")
        print("=" * 80)
        print(f"\n   Operator: {self.config.get('NINJA_SECRETARY_OPERATOR', coder_operator)}")
        print(f"   Model:    {self.config.get('NINJA_SECRETARY_MODEL', 'Not set')}")

    def _configure_models(self) -> None:
        """Configure models for each module with proper model picker."""
        print("\n" + "=" * 80)
        print("  🤖 MODEL CONFIGURATION")
        print("=" * 80)

        # NOTE: These hardcoded model lists are FALLBACKS ONLY for the legacy _configure_models() flow.
        # The recommended flow (_configure_coder_models, _configure_secretary) uses get_provider_models()
        # to dynamically load models from the actual operators. This method is kept for backwards
        # compatibility and manual module-specific model configuration.
        modules = [
            ("coder", "AI Code Assistant", OPENROUTER_MODELS),
            ("researcher", "Web Research Engine", PERPLEXITY_MODELS),
            ("secretary", "Documentation & Analysis", OPENROUTER_MODELS),
            ("resources", "Resource Templates", OPENROUTER_MODELS),
            ("prompts", "Prompt Management", OPENROUTER_MODELS),
        ]

        # Show current models
        print("\n📋 Current Models:")
        for module, desc, _ in modules:
            key = f"NINJA_{module.upper()}_MODEL"
            current = self.config.get(key, "Not set")
            print(f"  {desc:25} {current}")

        # Select module to configure
        choices = [
            Choice(
                value=(module, desc, models),
                name=f"{desc:25} [{self.config.get(f'NINJA_{module.upper()}_MODEL', 'Not set')}]",
            )
            for module, desc, models in modules
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

        module, desc, available_models = selected
        key = f"NINJA_{module.upper()}_MODEL"

        print(f"\n🎯 {desc} Model Configuration")

        # Build model choices grouped by provider
        model_choices = []
        current_provider = None

        for model_id, model_name, model_desc in available_models:
            provider = model_id.split("/")[0] if "/" in model_id else "native"
            if provider != current_provider:
                if current_provider is not None:
                    model_choices.append(Separator())
                provider_name = provider.upper() if provider != "native" else "Z.AI / GLM"
                model_choices.append(Separator(f"── {provider_name} ──"))
                current_provider = provider
            model_choices.append(Choice(value=model_id, name=f"{model_name:25} • {model_desc}"))

        # Add Z.ai models for coder
        # NOTE: ZAI_MODELS is a hardcoded FALLBACK list for the legacy _configure_models() flow.
        # The recommended flow (_configure_coder_models) uses get_provider_models() for dynamic loading.
        if module == "coder":
            model_choices.append(Separator())
            model_choices.append(Separator("── Z.AI / GLM (OpenCode Native) ──"))
            for model_id, model_name, model_desc in ZAI_MODELS:
                model_choices.append(Choice(value=model_id, name=f"{model_name:25} • {model_desc}"))

        model_choices.append(Separator())
        model_choices.append(Choice(value="__custom__", name="📝 Enter custom model name"))
        model_choices.append(Choice(value=None, name="← Back"))

        current_model = self.config.get(key, "")
        selected_model = inquirer.select(
            message=f"Select model for {desc}:",
            choices=model_choices,
            pointer="►",
            default=current_model if current_model in [m[0] for m in available_models] else None,
        ).execute()

        if selected_model is None:
            return

        if selected_model == "__custom__":
            # Allow custom model input
            selected_model = inquirer.text(
                message="Enter custom model name:",
                default=current_model,
                instruction="e.g., anthropic/claude-sonnet-4, qwen/qwen3-235b-a22b",
            ).execute()

        if selected_model:
            self._save_config(key, selected_model)
            print(f"\n✅ {desc} model updated to: {selected_model}")
        else:
            print("\n💡 No changes made")

    def _configure_task_based_models(self) -> None:
        """Configure task-based model selection."""
        print("\n" + "=" * 80)
        print("  📊 TASK-BASED MODEL SELECTION")
        print("=" * 80)

        # Show current task models
        task_models = TASK_MODEL_DEFAULTS

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
            Choice(
                value="quick",
                name=f"⚡ Quick Tasks Model     • Fast simple tasks (default: {TASK_MODEL_DEFAULTS[0][3]})",
            ),
            Choice(
                value="sequential",
                name=f"📊 Sequential Model     • Complex multi-step (default: {TASK_MODEL_DEFAULTS[1][3]})",
            ),
            Choice(
                value="parallel",
                name=f"🔀 Parallel Model       • High concurrency (default: {TASK_MODEL_DEFAULTS[2][3]})",
            ),
            Separator(),
            Choice(value="preferences", name="🎯 Model Preferences    • Cost vs Quality toggle"),
            Choice(
                value="reset_task_models", name="🔄 Reset to Defaults    • Restore default models"
            ),
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
                (
                    "anthropic/claude-haiku-4.5",
                    "Claude Haiku 4.5",
                    "Fast and cost-effective (Recommended)",
                ),
                ("claude-haiku-4", "Claude Haiku 4 (Claude Code)", "Fast via Claude Code"),
                ("glm-4.0", "GLM-4.0 (z.ai)", "Low cost, fast"),
                ("openai/gpt-4o-mini", "GPT-4o Mini", "OpenAI's fast model"),
            ]
        elif task_type == "sequential":
            recommended = [
                (
                    "anthropic/claude-haiku-4.5",
                    "Claude Haiku 4.5",
                    "Fast & cost-effective (Recommended)",
                ),
                (
                    "anthropic/claude-sonnet-4-5",
                    "Claude Sonnet 4.5",
                    "Higher quality (more expensive)",
                ),
                ("claude-sonnet-4-5", "Claude Sonnet 4.5 (Claude Code)", "Via Claude Code"),
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
            Choice(
                value="balanced",
                name="⚖️  Balanced       • Balance between cost and quality (Default)",
            ),
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

        # NOTE: Perplexity models are hardcoded here since Perplexity API doesn't support
        # dynamic model discovery. These are the official Perplexity Sonar models.
        perplexity_models = PERPLEXITY_MODELS

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
        print("\n📊 Current Status:")
        print(f"   Daemon Enabled: {'✓ Yes' if daemon_enabled else '✗ No'}")

        daemon_ports = {k: int(v) for k, v in DAEMON_CONFIG.items() if k != "NINJA_ENABLE_DAEMON"}

        print("\n🔌 Ports:")
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
        print("\n🔌 Port Configuration:")
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
        ide_configs = detect_ides()

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
            self._setup_claude_integration()
        elif selected == "opencode":
            self._setup_opencode_integration()
        else:
            print(f"\n💡  {selected.title()} configuration requires manual setup")
            print("   Refer to documentation for detailed instructions")

    def _setup_claude_integration(self) -> None:
        if not shutil.which("claude"):
            print("\n⚠️  Claude Code CLI not found")
            print("   Install from: https://claude.ai/download")
            return

        print("\n🔄 Setting up Claude Code MCP configuration...")
        success_count = register_claude_mcp()
        total = 3

        if success_count == total:
            print("\n✅ Claude Code integration completed successfully")
        else:
            print(f"\n⚠️  Claude Code integration completed with {success_count}/{total} servers")

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
            ("opencode-go", "OpenCode Go", "opencode auth opencode-go"),
            ("zai-coding-plan", "Z.AI Coding Plan", "opencode auth zai-coding-plan"),
            ("zai", "Z.ai / Zhipu AI", "opencode auth zai"),
            ("openrouter", "OpenRouter", "opencode auth openrouter"),
            ("opencode", "OpenCode (Free)", "opencode auth opencode"),
            ("anthropic", "Anthropic/Claude", "opencode auth anthropic"),
            ("google", "Google/Gemini", "opencode auth google"),
            ("openai", "OpenAI/GPT", "opencode auth openai"),
            ("github", "GitHub Copilot", "opencode auth github"),
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
            print("\n💡  No changes made")

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
            print("\n💡  Reset cancelled")


def run_power_configurator(config_path: str | None = None) -> int:
    """Run the power configurator (now uses modular UI)."""
    try:
        # Use the new modular UI instead of the old monolithic one
        from ninja_config.ui.component_setup import configure_secretary, run_coder_setup_flow
        from ninja_config.ui.main_menu import show_main_menu, show_welcome
        from ninja_config.ui.model_selector import (
            configure_model_slots,
            configure_task_based_models,
        )
        from ninja_config.ui.operator_config import (
            configure_opencode_auth,
            configure_operators,
            manage_api_keys,
        )
        from ninja_config.ui.settings import (
            advanced_settings,
            configure_daemon,
            configure_ide,
            configure_search,
            reset_configuration,
        )

        config_mgr = ConfigManager(config_path)

        # Show welcome
        show_welcome()

        # Main loop
        while True:
            config = config_mgr.list_all()
            choice = show_main_menu(config)

            if choice == "overview":
                from ninja_config.ui.main_menu import show_configuration_overview

                show_configuration_overview(config, config_mgr.config_file)
            elif choice == "coder_setup":
                run_coder_setup_flow(config_mgr, config)
            elif choice == "secretary_setup":
                configure_secretary(config_mgr, config)
            elif choice == "api_keys":
                manage_api_keys(config_mgr, config)
            elif choice == "operators":
                configure_operators(config_mgr, config)
            elif choice == "models":
                configure_model_slots(config_mgr, config)
            elif choice == "task_models":
                configure_task_based_models(config_mgr, config)
            elif choice == "search":
                configure_search(config_mgr, config)
            elif choice == "daemon":
                configure_daemon(config_mgr, config)
            elif choice == "ide":
                configure_ide(config_mgr, config)
            elif choice == "opencode_auth":
                configure_opencode_auth(config_mgr, config)
            elif choice == "advanced":
                advanced_settings(config_mgr, config)
            elif choice == "reset":
                reset_configuration(config_mgr)
            elif choice == "exit":
                print("\n👋 Configuration saved. Goodbye!")
                break
            else:
                print(f"\n⚠️  Unknown choice: {choice}")

        return 0
    except KeyboardInterrupt:
        print("\n\n👋 Configuration session ended")
        return 0
    except Exception as e:
        print(f"\n❌ Configuration error: {e}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    config_path = sys.argv[1] if len(sys.argv) > 1 else None
    sys.exit(run_power_configurator(config_path))
