"""
Modern TUI installer for ninja-mcp with comprehensive key collection and model selection.
"""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


# Try multiple import patterns for InquirerPy compatibility
try:
    from InquirerPy import inquirer
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


class TUIInstaller:
    """Interactive TUI installer with comprehensive configuration."""

    def __init__(self):
        """Initialize installer."""
        self.config_data = {}
        self.detected_tools = {}
        self.detected_ide_configs = {}

    def print_header(self) -> None:
        """Print installation header."""
        print("\n" + "═" * 80)
        print("  🥷 NINJA MCP - ADVANCED TUI INSTALLER")
        print("  Complete setup with API keys, model selection, and IDE integration")
        print("═" * 80)

    def print_success(self, message: str) -> None:
        """Print success message."""
        print(f"✅ {message}")

    def print_info(self, message: str) -> None:
        """Print info message."""
        print(f"i  {message}")

    def print_warning(self, message: str) -> None:
        """Print warning message."""
        print(f"⚠️  {message}")

    def detect_system(self) -> dict[str, str]:
        """Detect system information."""
        system_info = {
            "os": "unknown",
            "arch": "unknown",
            "shell": os.environ.get("SHELL", "unknown"),
        }

        # OS detection
        if sys.platform.startswith("linux"):
            system_info["os"] = "linux"
        elif sys.platform == "darwin":
            system_info["os"] = "macos"
        elif sys.platform == "win32":
            system_info["os"] = "windows"

        # Architecture detection
        system_info["arch"] = os.uname().machine if hasattr(os, "uname") else "unknown"

        return system_info

    def check_python_version(self) -> bool:
        """Check if Python version is 3.11+."""
        version = sys.version_info
        if version.major >= 3 and version.minor >= 11:
            self.print_success(f"Python {version.major}.{version.minor}")
            return True
        else:
            print(f"❌ Python 3.11+ required (you have {version.major}.{version.minor})")
            return False

    def check_uv(self) -> bool:
        """Check if uv is installed."""
        if shutil.which("uv"):
            result = subprocess.run(
                ["uv", "--version"], capture_output=True, text=True, check=False
            )
            version = result.stdout.strip().split()[1] if result.stdout else "unknown"
            self.print_success(f"uv {version}")
            return True
        else:
            self.print_warning("uv package manager not found")
            result = inquirer.confirm(
                message="Install uv package manager?",
                default=True,
            )
            install = result.execute() if hasattr(result, "execute") else result

            if install:
                print("🔄 Installing uv...")
                result = subprocess.run(
                    "curl -LsSf https://astral.sh/uv/install.sh | sh",
                    shell=True,
                    capture_output=True,
                    text=True,
                    check=False,
                )

                if result.returncode == 0:
                    self.print_success("uv installed successfully")
                    # Update PATH
                    local_bin = Path.home() / ".local" / "bin"
                    os.environ["PATH"] = f"{local_bin}:{os.environ.get('PATH', '')}"
                    return True
                else:
                    print(f"❌ Failed to install uv: {result.stderr}")
                    return False
            return False

    def detect_installed_tools(self) -> dict[str, str]:
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

        # Check for cursor
        if shutil.which("cursor"):
            tools["cursor"] = shutil.which("cursor")

        return tools

    def detect_ide_configs(self) -> dict[str, str]:
        """Detect IDE configuration files."""
        configs = {}

        # Claude Code
        claude_configs = [
            Path.home() / ".config" / "claude" / "mcp.json",
            Path.home() / ".claude.json",
        ]
        for config_path in claude_configs:
            if config_path.exists():
                configs["claude"] = str(config_path)
                break

        # VS Code
        vscode_configs = [
            Path.home() / ".config" / "Code" / "User" / "settings.json",
            Path.home() / "Library" / "Application Support" / "Code" / "User" / "settings.json",
        ]
        for config_path in vscode_configs:
            if config_path.exists():
                configs["vscode"] = str(config_path)
                break

        # Zed
        zed_config = Path.home() / ".config" / "zed" / "settings.json"
        if zed_config.exists():
            configs["zed"] = str(zed_config)

        # OpenCode
        opencode_configs = [
            Path.home() / ".opencode.json",
            Path.home() / ".config" / "opencode" / ".opencode.json",
        ]
        for config_path in opencode_configs:
            if config_path.exists():
                configs["opencode"] = str(config_path)
                break

        return configs

    def select_installation_type(self) -> str:
        """Select installation type."""
        result = inquirer.select(
            message="📦 Installation Type:",
            choices=[
                Choice(
                    value="full",
                    name="Full Installation  •  All modules with advanced features",
                ),
                Choice(
                    value="minimal",
                    name="Minimal Installation  •  Core modules only (coder, resources)",
                ),
                Choice(
                    value="custom",
                    name="Custom Installation  •  Select specific modules",
                ),
            ],
            pointer="►",
        )

        return result.execute() if hasattr(result, "execute") else result

    def select_modules(self) -> list[str]:
        """Select modules for installation."""
        all_modules = [
            ("coder", "AI code assistant with Aider/OpenCode/Gemini support"),
            ("researcher", "Web research with DuckDuckGo/Perplexity"),
            ("secretary", "File operations and codebase analysis"),
            ("resources", "Resource templates and prompts"),
            ("prompts", "Prompt management and chaining"),
        ]

        choices = [
            Choice(
                value=name,
                name=f"{name.title()}  •  {desc}",
                enabled=True,
            )
            for name, desc in all_modules
        ]

        result = inquirer.checkbox(
            message="🎯 Select Modules to Install:",
            choices=choices,
            pointer="►",
            instruction="Space to select, Enter to confirm",
        )

        selected = result.execute() if hasattr(result, "execute") else result
        return selected if selected else ["coder", "resources"]

    def collect_api_keys(self) -> dict[str, str]:
        """Collect all required API keys."""
        keys = {}

        print("\n🔑 API KEY CONFIGURATION")
        print("   Securely store your API keys for AI services")
        print("   " + "─" * 50)

        # OpenRouter API Key (primary)
        existing_key = os.environ.get("OPENROUTER_API_KEY") or os.environ.get("OPENAI_API_KEY")
        if existing_key:
            masked = (
                f"{existing_key[:8]}...{existing_key[-4:]}" if len(existing_key) > 12 else "***"
            )
            result = inquirer.confirm(
                message=f"Use existing API key ({masked})?",
                default=True,
            )
            use_existing = result.execute() if hasattr(result, "execute") else result

            if use_existing:
                keys["OPENROUTER_API_KEY"] = existing_key
            else:
                result = inquirer.secret(
                    message="OpenRouter API Key:",
                    instruction="Get from https://openrouter.ai/keys",
                )
                api_key = result.execute() if hasattr(result, "execute") else result
                if api_key:
                    keys["OPENROUTER_API_KEY"] = api_key
        else:
            result = inquirer.secret(
                message="OpenRouter API Key:",
                instruction="Get from https://openrouter.ai/keys",
            )
            api_key = result.execute() if hasattr(result, "execute") else result
            if api_key:
                keys["OPENROUTER_API_KEY"] = api_key

        # Additional keys for researcher module
        if "researcher" in self.config_data.get("modules", []):
            print("\n🌐 Search Provider Configuration")

            result = inquirer.select(
                message="Select Search Provider:",
                choices=[
                    Choice("duckduckgo", name="DuckDuckGo  •  Free, no API key required"),
                    Choice("serper", name="Serper.dev  •  Google Search API"),
                    Choice("perplexity", name="Perplexity AI  •  AI-powered search"),
                ],
                pointer="►",
            )
            search_provider = result.execute() if hasattr(result, "execute") else result
            keys["NINJA_SEARCH_PROVIDER"] = search_provider

            if search_provider == "serper":
                result = inquirer.secret(
                    message="Serper.dev API Key:",
                    instruction="Get from https://serper.dev",
                )
                serper_key = result.execute() if hasattr(result, "execute") else result
                if serper_key:
                    keys["SERPER_API_KEY"] = serper_key

            elif search_provider == "perplexity":
                result = inquirer.secret(
                    message="Perplexity API Key:",
                    instruction="Get from https://www.perplexity.ai/settings/api",
                )
                perplexity_key = result.execute() if hasattr(result, "execute") else result
                if perplexity_key:
                    keys["PERPLEXITY_API_KEY"] = perplexity_key

        # Google API Key for Gemini
        if "gemini" in self.detected_tools:
            result = inquirer.secret(
                message="Google API Key (for Gemini):",
                instruction="Optional, for native Gemini integration",
            )
            google_key = result.execute() if hasattr(result, "execute") else result
            if google_key:
                keys["GOOGLE_API_KEY"] = google_key

        return keys

    def fetch_model_recommendations(self, category: str) -> list[dict[str, Any]]:
        """Fetch model recommendations from LiveBench or fallback."""
        try:
            script_path = (
                Path(__file__).parent.parent.parent / "scripts" / "get_recommended_models.py"
            )
            if script_path.exists():
                result = subprocess.run(
                    [sys.executable, str(script_path), category],
                    capture_output=True,
                    text=True,
                    check=True,
                    timeout=15,
                )
                if result.stdout.strip():
                    return json.loads(result.stdout)
        except Exception:
            pass

        # Fallback models
        fallback_models = {
            "coder": [
                {
                    "name": "anthropic/claude-haiku-4.5-20250929",
                    "tier": "🏆 Recommended",
                    "price": 0.15,
                    "speed": "⚡ Very Fast",
                },
                {
                    "name": "qwen/qwen-2.5-coder-32b-instruct",
                    "tier": "💰 Budget",
                    "price": 0.30,
                    "speed": "🚀 Fast",
                },
                {
                    "name": "google/gemini-2.0-flash-exp",
                    "tier": "⚡ Speed",
                    "price": 0.075,
                    "speed": "⚡ Very Fast",
                },
                {
                    "name": "anthropic/claude-sonnet-4",
                    "tier": "🎯 Quality",
                    "price": 3.0,
                    "speed": "⚖️ Balanced",
                },
                {
                    "name": "openai/gpt-4o-mini",
                    "tier": "💰 Budget",
                    "price": 0.15,
                    "speed": "⚡ Very Fast",
                },
            ],
            "researcher": [
                {
                    "name": "anthropic/claude-sonnet-4",
                    "tier": "🏆 Recommended",
                    "price": 3.0,
                    "speed": "⚖️ Balanced",
                },
                {
                    "name": "openai/gpt-4o",
                    "tier": "🎯 Quality",
                    "price": 3.0,
                    "speed": "⚖️ Balanced",
                },
                {
                    "name": "google/gemini-2.0-flash-exp",
                    "tier": "⚡ Speed",
                    "price": 0.075,
                    "speed": "⚡ Very Fast",
                },
                {
                    "name": "anthropic/claude-sonnet-3.5",
                    "tier": "⚖️ Balanced",
                    "price": 3.0,
                    "speed": "⚖️ Balanced",
                },
                {
                    "name": "deepseek/deepseek-chat",
                    "tier": "💰 Budget",
                    "price": 0.14,
                    "speed": "🚀 Fast",
                },
            ],
            "secretary": [
                {
                    "name": "google/gemini-2.0-flash-exp",
                    "tier": "🏆 Recommended",
                    "price": 0.075,
                    "speed": "⚡ Very Fast",
                },
                {
                    "name": "anthropic/claude-haiku-4.5-20250929",
                    "tier": "⚡ Speed",
                    "price": 0.15,
                    "speed": "⚡ Very Fast",
                },
                {
                    "name": "openai/gpt-4o-mini",
                    "tier": "💰 Budget",
                    "price": 0.15,
                    "speed": "⚡ Very Fast",
                },
                {
                    "name": "qwen/qwen-2.5-coder-32b-instruct",
                    "tier": "⚖️ Balanced",
                    "price": 0.30,
                    "speed": "🚀 Fast",
                },
                {
                    "name": "deepseek/deepseek-chat",
                    "tier": "💰 Budget",
                    "price": 0.14,
                    "speed": "🚀 Fast",
                },
            ],
        }

        return fallback_models.get(category, fallback_models["coder"])

    def select_models(self) -> dict[str, str]:
        """Select models for each module."""
        models = {}

        print("\n🤖 MODEL SELECTION")
        print("   Choose AI models for each module")
        print("   " + "─" * 50)

        modules_with_models = [
            module
            for module in self.config_data.get("modules", [])
            if module in ["coder", "researcher", "secretary"]
        ]

        for module in modules_with_models:
            print(f"\n🎯 {module.title()} Module:")

            # Fetch recommendations
            recommendations = self.fetch_model_recommendations(module)

            # Build choices
            choices = []
            for i, model in enumerate(recommendations[:5]):
                price_str = f"${model['price']:.2f}/1M" if model["price"] > 0 else "Free"
                choices.append(
                    Choice(
                        value=model["name"],
                        name=f"{model['tier']} | {model['name']} | {price_str} | {model['speed']}",
                    )
                )

            # Add custom option
            choices.append(Separator())
            choices.append(Choice(value="custom", name="Enter custom model name"))

            # Select model
            result = inquirer.select(
                message=f"Select {module} model:",
                choices=choices,
                pointer="►",
            )
            selected = result.execute() if hasattr(result, "execute") else result

            if selected == "custom":
                result = inquirer.text(
                    message="Enter model name:",
                    instruction="e.g., anthropic/claude-opus-4",
                )
                custom_model = result.execute() if hasattr(result, "execute") else result
                models[f"NINJA_{module.upper()}_MODEL"] = custom_model
            else:
                models[f"NINJA_{module.upper()}_MODEL"] = selected

        return models

    def select_code_cli(self) -> str:
        """Select AI code CLI tool."""
        print("\n💻 AI CODE CLI SELECTION")
        print("   Choose your preferred AI coding assistant")
        print("   " + "─" * 50)

        # Build tool choices
        tool_choices = []

        # Add detected tools
        for name, path in self.detected_tools.items():
            tool_choices.append(Choice(value=path, name=f"{name.title()}  •  {path}"))

        # Add common tools
        common_tools = [
            ("aider", "Aider Chat - OpenRouter integration"),
            ("opencode", "OpenCode - Multi-provider CLI"),
            ("gemini", "Gemini CLI - Google models"),
            ("cursor", "Cursor - IDE with AI"),
        ]

        for name, desc in common_tools:
            if name not in self.detected_tools:
                tool_choices.append(
                    Choice(value=name, name=f"{name.title()}  •  {desc} (will be installed)")
                )

        # Add custom option
        tool_choices.append(Separator())
        tool_choices.append(Choice(value="custom", name="Enter custom path"))

        result = inquirer.select(
            message="Select AI Code CLI:",
            choices=tool_choices,
            pointer="►",
        )
        selected = result.execute() if hasattr(result, "execute") else result

        # Handle installation if needed
        if selected in ["aider", "opencode", "gemini", "cursor"]:
            tool_name = selected
            print(f"\n🔄 Installing {tool_name}...")

            if tool_name == "aider":
                result = subprocess.run(
                    ["uv", "tool", "install", "aider-chat"],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if result.returncode == 0:
                    self.print_success("Aider installed")
                    return shutil.which("aider") or "aider"
                else:
                    self.print_warning(f"Failed to install aider: {result.stderr}")
                    return "aider"
            else:
                print(f"i  Please install {tool_name} manually")
                return tool_name

        elif selected == "custom":
            result = inquirer.text(
                message="Enter path to AI Code CLI:",
                validate=PathValidator(),
            )
            custom_path = result.execute() if hasattr(result, "execute") else result
            return custom_path
        else:
            return selected

    def configure_daemon(self) -> bool:
        """Configure daemon mode."""
        print("\n⚙️  DAEMON CONFIGURATION")
        print("   Run modules as background services")
        print("   " + "─" * 50)

        result = inquirer.confirm(
            message="Enable daemon mode? (recommended)",
            default=True,
        )
        enable_daemon = result.execute() if hasattr(result, "execute") else result
        return enable_daemon

    def configure_ide_integration(self) -> list[str]:
        """Configure IDE integration."""
        if not self.detected_ide_configs:
            return []

        print("\n🖥️  IDE INTEGRATION")
        print("   Connect Ninja MCP to your editors")
        print("   " + "─" * 50)

        # Build IDE choices
        ide_choices = []
        for ide, config_path in self.detected_ide_configs.items():
            ide_choices.append(Choice(value=ide, name=f"{ide.title()}  •  Config: {config_path}"))

        if not ide_choices:
            self.print_info("No supported IDEs detected")
            return []

        result = inquirer.checkbox(
            message="Select IDEs to configure:",
            choices=ide_choices,
            pointer="►",
        )
        selected_ides = result.execute() if hasattr(result, "execute") else result
        return selected_ides if selected_ides else []

    def save_configuration(
        self, api_keys: dict[str, str], models: dict[str, str], code_cli: str
    ) -> bool:
        """Save configuration to ~/.ninja-mcp.env."""
        config_file = Path.home() / ".ninja-mcp.env"

        print(f"\n💾 Saving configuration to {config_file}")

        # Combine all configuration
        config_lines = [
            "# Ninja MCP Configuration",
            f"# Generated on {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            "# ===================================================================",
            "# Common Configuration",
            "# ===================================================================",
            "",
        ]

        # Add API keys
        for key, value in api_keys.items():
            if value:  # Only save non-empty values
                config_lines.append(f'export {key}="{value}"')

        # Add models
        config_lines.append("")
        config_lines.append("# ===================================================================")
        config_lines.append("# Module Models")
        config_lines.append("# ===================================================================")
        config_lines.append("")

        for key, value in models.items():
            if value:  # Only save non-empty values
                config_lines.append(f'export {key}="{value}"')

        # Add code CLI
        if code_cli:
            config_lines.append("")
            config_lines.append(
                "# ==================================================================="
            )
            config_lines.append("# Code CLI")
            config_lines.append(
                "# ==================================================================="
            )
            config_lines.append("")
            config_lines.append(f'export NINJA_CODE_BIN="{code_cli}"')

        # Add daemon configuration
        config_lines.append("")
        config_lines.append("# ===================================================================")
        config_lines.append("# Daemon Configuration")
        config_lines.append("# ===================================================================")
        config_lines.append("")
        config_lines.append("export NINJA_ENABLE_DAEMON=true")
        config_lines.append("export NINJA_CODER_PORT=8100")
        config_lines.append("export NINJA_RESEARCHER_PORT=8101")
        config_lines.append("export NINJA_SECRETARY_PORT=8102")
        config_lines.append("export NINJA_RESOURCES_PORT=8106")
        config_lines.append("export NINJA_PROMPTS_PORT=8107")

        # Write configuration
        try:
            config_file.parent.mkdir(parents=True, exist_ok=True)
            config_file.write_text("\n".join(config_lines) + "\n")
            config_file.chmod(0o600)  # Secure permissions
            self.print_success("Configuration saved")
            return True
        except Exception as e:
            print(f"❌ Failed to save configuration: {e}")
            return False

    def install_ninja_mcp(self, install_type: str, modules: list[str]) -> bool:
        """Install ninja-mcp with selected modules."""
        print("\n🔄 Installing ninja-mcp...")

        # Determine installation extras
        if install_type == "full":
            extras = "[all]"
        elif install_type == "minimal":
            extras = "[coder,resources]"
        else:
            extras = f"[{','.join(modules)}]"

        print(f"   Installing with extras: {extras}")

        # Check if we're in dev directory
        cwd = Path.cwd()
        if (cwd / "pyproject.toml").exists():
            print(f"   Installing from local source: {cwd}")
            cmd = ["uv", "tool", "install", "--force", f"{cwd}{extras}"]
        else:
            print("   Installing from PyPI...")
            cmd = ["uv", "tool", "install", "--force", f"ninja-mcp{extras}"]

        result = subprocess.run(cmd, capture_output=True, text=True, check=False)

        if result.returncode == 0:
            self.print_success("ninja-mcp installed successfully")
            return True
        else:
            print(f"❌ Installation failed: {result.stderr}")
            return False

    def verify_installation(self) -> bool:
        """Verify all components are installed correctly."""
        print("\n🔍 Verifying installation...")

        all_ok = True
        commands = [
            "ninja-config",
            "ninja-coder",
            "ninja-researcher",
            "ninja-secretary",
            "ninja-resources",
            "ninja-prompts",
        ]

        for cmd in commands:
            if shutil.which(cmd):
                self.print_success(cmd)
            else:
                print(f"❌ {cmd} not found")
                all_ok = False

        return all_ok

    def show_completion_summary(self, selected_ides: list[str]) -> None:
        """Show installation completion summary."""
        print("\n" + "🎉" * 80)
        print("  🎉 INSTALLATION COMPLETE!")
        print("  Ninja MCP is ready to use")
        print("🎉" * 80)

        print("\n📋 QUICK START:\n")
        print("1. Load configuration:")
        print("   source ~/.ninja-mcp.env")
        print()
        print("2. Select operator and model:")
        print("   ninja-config select-model")
        print()
        print("3. Configure IDE integration:")
        if selected_ides:
            for ide in selected_ides:
                print(f"   ninja-config setup-{ide}")
        else:
            print("   ninja-config setup-claude  # or setup other IDEs")
        print()
        print("4. Verify installation:")
        print("   ninja-config doctor")
        print()
        print("5. Start using Ninja MCP in your IDE!")
        print()
        print("📚 Documentation: https://github.com/angkira/ninja-cli-mcp")
        print()

    def run(self) -> int:
        """Run the interactive installer."""
        self.print_header()

        # System detection
        system_info = self.detect_system()
        print(f"\n🖥️  System: {system_info['os'].title()} {system_info['arch']}")

        # Check prerequisites
        if not self.check_python_version():
            return 1

        if not self.check_uv():
            return 1

        # Detect installed tools
        self.detected_tools = self.detect_installed_tools()
        if self.detected_tools:
            print(f"\n🔧 Detected Tools: {', '.join(self.detected_tools.keys())}")

        # Detect IDE configs
        self.detected_ide_configs = self.detect_ide_configs()
        if self.detected_ide_configs:
            print(f"🖥️  Detected IDEs: {', '.join(self.detected_ide_configs.keys())}")

        # Select installation type
        install_type = self.select_installation_type()

        # Select modules
        if install_type == "custom":
            modules = self.select_modules()
        elif install_type == "minimal":
            modules = ["coder", "resources"]
        else:  # full
            modules = ["coder", "researcher", "secretary", "resources", "prompts"]

        self.config_data["modules"] = modules
        print(f"\n📦 Selected modules: {', '.join(modules)}")

        # Install ninja-mcp
        if not self.install_ninja_mcp(install_type, modules):
            return 1

        # Collect API keys
        api_keys = self.collect_api_keys()

        # Select models
        models = self.select_models()

        # Select code CLI
        code_cli = self.select_code_cli()

        # Configure daemon
        enable_daemon = self.configure_daemon()
        if enable_daemon:
            api_keys["NINJA_ENABLE_DAEMON"] = "true"

        # Configure IDE integration
        selected_ides = self.configure_ide_integration()

        # Save configuration
        if not self.save_configuration(api_keys, models, code_cli):
            return 1

        # Verify installation
        if not self.verify_installation():
            self.print_warning("Some components failed to install")
            print("   Run: ninja-config doctor")

        # Show completion summary
        self.show_completion_summary(selected_ides)

        return 0


def run_tui_installer() -> int:
    """Run the TUI installer."""
    installer = TUIInstaller()
    return installer.run()


if __name__ == "__main__":
    sys.exit(run_tui_installer())
