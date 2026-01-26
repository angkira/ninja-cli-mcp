"""
Interactive model selector for ninja-coder.

Allows selecting:
1. Operator (opencode, aider, gemini-cli, etc.)
2. Model based on operator capabilities
"""

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class Model:
    """A model available for a specific operator."""

    id: str
    name: str
    description: str
    provider: str
    recommended: bool = False


@dataclass
class Operator:
    """A code CLI operator (opencode, aider, etc.)."""

    id: str
    name: str
    binary_name: str
    description: str
    binary_path: Optional[str] = None
    models: list[Model] = None

    def __post_init__(self):
        if self.models is None:
            self.models = []

    @property
    def is_installed(self) -> bool:
        """Check if this operator is installed."""
        return self.binary_path is not None

    def detect(self) -> bool:
        """Detect if this operator is installed and find its path."""
        binary = shutil.which(self.binary_name)
        if binary:
            self.binary_path = binary
            return True
        return False


# Available operators with their models
OPERATORS = [
    Operator(
        id="opencode",
        name="OpenCode",
        binary_name="opencode",
        description="Multi-provider CLI (75+ providers, native z.ai support)",
        models=[
            # Anthropic
            Model(
                "anthropic/claude-sonnet-4-5",
                "Claude Sonnet 4.5",
                "Latest Claude - Balanced performance & cost",
                "anthropic",
                recommended=True,
            ),
            Model(
                "anthropic/claude-opus-4-5",
                "Claude Opus 4.5",
                "Most powerful Claude model",
                "anthropic",
            ),
            Model(
                "anthropic/claude-sonnet-3-5",
                "Claude Sonnet 3.5",
                "Previous generation - Fast & capable",
                "anthropic",
            ),
            Model(
                "anthropic/claude-haiku-3-5",
                "Claude Haiku 3.5",
                "Fast & cost-effective for simple tasks",
                "anthropic",
            ),
            # Google
            Model(
                "google/gemini-2.0-flash-exp",
                "Gemini 2.0 Flash",
                "Fast, experimental, very cost-effective",
                "google",
            ),
            Model(
                "google/gemini-1.5-pro",
                "Gemini 1.5 Pro",
                "Balanced Google model",
                "google",
            ),
            Model(
                "google/gemini-1.5-flash",
                "Gemini 1.5 Flash",
                "Fast Google model",
                "google",
            ),
            # OpenAI
            Model(
                "openai/gpt-4o",
                "GPT-4o",
                "Latest OpenAI model - Multimodal",
                "openai",
            ),
            Model(
                "openai/gpt-4-turbo",
                "GPT-4 Turbo",
                "Fast GPT-4 variant",
                "openai",
            ),
            Model(
                "openai/o1-preview",
                "o1-preview",
                "Reasoning model - Slow but deep",
                "openai",
            ),
            # GitHub
            Model(
                "github/gpt-4o",
                "GPT-4o (via GitHub)",
                "Access via GitHub Copilot",
                "github",
            ),
        ],
    ),
    Operator(
        id="aider",
        name="Aider",
        binary_name="aider",
        description="OpenRouter-based CLI (requires OPENROUTER_API_KEY)",
        models=[
            Model(
                "anthropic/claude-sonnet-4-5",
                "Claude Sonnet 4.5",
                "Latest Claude via OpenRouter",
                "anthropic",
                recommended=True,
            ),
            Model(
                "anthropic/claude-opus-4-5",
                "Claude Opus 4.5",
                "Most powerful via OpenRouter",
                "anthropic",
            ),
            Model(
                "anthropic/claude-sonnet-3.5",
                "Claude Sonnet 3.5",
                "Previous generation via OpenRouter",
                "anthropic",
            ),
            Model(
                "google/gemini-2.0-flash-exp",
                "Gemini 2.0 Flash",
                "Fast Google model via OpenRouter",
                "google",
            ),
            Model(
                "openai/gpt-4o",
                "GPT-4o",
                "Latest OpenAI via OpenRouter",
                "openai",
            ),
            Model(
                "deepseek/deepseek-coder",
                "DeepSeek Coder",
                "Specialized coding model",
                "deepseek",
            ),
            Model(
                "qwen/qwen-2.5-coder-32b-instruct",
                "Qwen 2.5 Coder 32B",
                "Open source coding model",
                "qwen",
            ),
        ],
    ),
    Operator(
        id="gemini",
        name="Gemini CLI",
        binary_name="gemini",
        description="Google Gemini native CLI",
        models=[
            Model(
                "gemini-2.0-flash-exp",
                "Gemini 2.0 Flash",
                "Latest experimental - Very fast",
                "google",
                recommended=True,
            ),
            Model(
                "gemini-1.5-pro",
                "Gemini 1.5 Pro",
                "Balanced performance",
                "google",
            ),
            Model(
                "gemini-1.5-flash",
                "Gemini 1.5 Flash",
                "Fast & cost-effective",
                "google",
            ),
        ],
    ),
]


def detect_operators() -> list[Operator]:
    """Detect which operators are installed."""
    installed = []
    for operator in OPERATORS:
        if operator.detect():
            installed.append(operator)
    return installed


def check_operator_auth(operator: Operator) -> dict[str, bool]:
    """Check which providers are authenticated for an operator."""
    auth_status = {}

    if operator.id == "opencode":
        # Check opencode auth status
        try:
            result = subprocess.run(
                ["opencode", "auth", "list"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            output = result.stdout.lower()

            auth_status["anthropic"] = "anthropic" in output
            auth_status["google"] = "google" in output
            auth_status["openai"] = "openai" in output
            auth_status["github"] = "github" in output or "copilot" in output
        except Exception:
            pass

    elif operator.id == "aider":
        # Aider uses OpenRouter API key
        auth_status["openrouter"] = bool(
            os.getenv("OPENROUTER_API_KEY") or os.getenv("OPENAI_API_KEY")
        )

    elif operator.id == "gemini":
        # Gemini uses Google API key
        auth_status["google"] = bool(os.getenv("GOOGLE_API_KEY"))

    return auth_status


def select_operator_interactive() -> Optional[Operator]:
    """Interactive operator selection."""
    print("\n" + "=" * 70)
    print("  🥷 NINJA CODER - OPERATOR SELECTION")
    print("=" * 70)

    installed = detect_operators()

    if not installed:
        print("\n❌ No operators found!")
        print("\nAvailable operators:")
        for op in OPERATORS:
            print(f"  • {op.name} - Install: {op.binary_name}")
        print("\nInstall an operator first, then run this again.")
        return None

    print("\n📦 Available Operators:\n")

    for idx, op in enumerate(installed, 1):
        auth_status = check_operator_auth(op)
        auth_count = sum(auth_status.values())

        print(f"{idx}. {op.name}")
        print(f"   {op.description}")
        print(f"   Binary: {op.binary_path}")

        if auth_status:
            print(f"   Auth: {auth_count} provider(s) authenticated")
            for provider, is_auth in auth_status.items():
                status = "✓" if is_auth else "✗"
                print(f"     {status} {provider}")
        print()

    # Get selection
    while True:
        try:
            choice = input(f"Select operator [1-{len(installed)}] or 'q' to quit: ").strip()
            if choice.lower() == "q":
                return None

            idx = int(choice) - 1
            if 0 <= idx < len(installed):
                return installed[idx]

            print(f"Invalid choice. Please enter 1-{len(installed)}")
        except (ValueError, KeyboardInterrupt):
            print("\nCancelled.")
            return None


def select_model_interactive(operator: Operator) -> Optional[Model]:
    """Interactive model selection for a specific operator."""
    print("\n" + "=" * 70)
    print(f"  🤖 MODEL SELECTION - {operator.name}")
    print("=" * 70)

    # Get auth status to filter models
    auth_status = check_operator_auth(operator)

    # Group models by provider
    by_provider = {}
    for model in operator.models:
        provider = model.provider
        if provider not in by_provider:
            by_provider[provider] = []
        by_provider[provider].append(model)

    print("\n📋 Available Models:\n")

    idx = 1
    model_map = {}

    for provider, models in sorted(by_provider.items()):
        # Check if provider is authenticated
        is_auth = auth_status.get(provider, False)
        auth_symbol = "✓" if is_auth else "✗"

        print(f"  {auth_symbol} {provider.upper()}")

        for model in models:
            rec = " [RECOMMENDED]" if model.recommended else ""
            print(f"    {idx}. {model.name}{rec}")
            print(f"       {model.description}")
            print(f"       ID: {model.id}")
            print()
            model_map[idx] = model
            idx += 1

    # Show warning if some providers not authenticated
    unauth_providers = [p for p, auth in auth_status.items() if not auth]
    if unauth_providers:
        print(f"⚠️  Some providers not authenticated: {', '.join(unauth_providers)}")
        print(f"   Models from these providers may not work.\n")

    # Get selection
    while True:
        try:
            choice = input(
                f"Select model [1-{len(model_map)}] or 'q' to quit: "
            ).strip()
            if choice.lower() == "q":
                return None

            idx = int(choice)
            if idx in model_map:
                return model_map[idx]

            print(f"Invalid choice. Please enter 1-{len(model_map)}")
        except (ValueError, KeyboardInterrupt):
            print("\nCancelled.")
            return None


def update_configuration(operator: Operator, model: Model) -> bool:
    """Update ninja-coder configuration with selected operator and model."""
    print("\n" + "=" * 70)
    print("  💾 UPDATING CONFIGURATION")
    print("=" * 70)

    # Update ~/.ninja-mcp.env
    env_file = Path.home() / ".ninja-mcp.env"
    print(f"\n1. Updating {env_file}...")

    try:
        # Read existing config
        lines = []
        if env_file.exists():
            lines = env_file.read_text().splitlines()

        # Update or add NINJA_CODE_BIN and NINJA_MODEL
        updated = False
        for i, line in enumerate(lines):
            if line.startswith("NINJA_CODE_BIN="):
                lines[i] = f"NINJA_CODE_BIN={operator.binary_path}"
                updated = True
            elif line.startswith("NINJA_MODEL="):
                lines[i] = f"NINJA_MODEL={model.id}"
                updated = True

        if not updated:
            lines.extend(
                [
                    f"NINJA_CODE_BIN={operator.binary_path}",
                    f"NINJA_MODEL={model.id}",
                ]
            )

        # Write back
        env_file.write_text("\n".join(lines) + "\n")
        print("   ✓ Updated .ninja-mcp.env")
    except Exception as e:
        print(f"   ✗ Failed to update .ninja-mcp.env: {e}")
        return False

    # Update ~/.claude.json
    claude_config = Path.home() / ".claude.json"
    print(f"\n2. Updating {claude_config}...")

    # Check if Claude Code is running
    try:
        result = subprocess.run(
            ["pgrep", "-f", "claude|Claude"],
            capture_output=True,
            timeout=2,
        )
        if result.returncode == 0:
            print("   ⚠️  Claude Code is running!")
            print("   Configuration will be updated, but you need to restart Claude Code")
            print("   for changes to take effect.")
    except Exception:
        pass

    try:
        if not claude_config.exists():
            print("   ⚠️  Claude config not found - skipping")
            return True

        # Read config
        config = json.loads(claude_config.read_text())

        # Update ninja-coder MCP server
        if "mcpServers" not in config:
            config["mcpServers"] = {}

        if "ninja-coder" not in config["mcpServers"]:
            config["mcpServers"]["ninja-coder"] = {
                "type": "stdio",
                "command": "ninja-coder",
                "args": [],
            }

        config["mcpServers"]["ninja-coder"]["env"] = {
            "NINJA_CODE_BIN": operator.binary_path,
            "NINJA_MODEL": model.id,
        }

        # Write back
        claude_config.write_text(json.dumps(config, indent=2))
        print("   ✓ Updated .claude.json")
    except Exception as e:
        print(f"   ✗ Failed to update .claude.json: {e}")
        return False

    return True


def print_summary(operator: Operator, model: Model):
    """Print configuration summary."""
    print("\n" + "=" * 70)
    print("  ✅ CONFIGURATION COMPLETE")
    print("=" * 70)

    print(f"\nOperator: {operator.name}")
    print(f"  Binary: {operator.binary_path}")

    print(f"\nModel: {model.name}")
    print(f"  ID: {model.id}")
    print(f"  Provider: {model.provider}")
    print(f"  {model.description}")

    print("\n📝 Next Steps:")
    print("  1. Restart Claude Code (if running)")
    print("  2. Config will be automatically detected")
    print("  3. Test by asking Claude Code to write some code!")

    print("\n💡 To change later, run:")
    print("     ninja-config select-model")
    print()


def run_interactive_selector():
    """Run the full interactive model selector."""
    # Select operator
    operator = select_operator_interactive()
    if not operator:
        return False

    # Select model
    model = select_model_interactive(operator)
    if not model:
        return False

    # Confirm
    print("\n" + "=" * 70)
    print("  🔍 CONFIRM SELECTION")
    print("=" * 70)
    print(f"\nOperator: {operator.name}")
    print(f"Model:    {model.name} ({model.id})")

    confirm = input("\nApply this configuration? [Y/n]: ").strip().lower()
    if confirm and confirm != "y":
        print("Cancelled.")
        return False

    # Update configuration
    success = update_configuration(operator, model)

    if success:
        print_summary(operator, model)

    return success


if __name__ == "__main__":
    run_interactive_selector()
