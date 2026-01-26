"""
Interactive model selector for ninja-coder.

Dynamically detects operators and queries their available models.
NO hardcoded model lists - everything is queried from the actual operators.
"""

import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

try:
    from InquirerPy import inquirer
    from InquirerPy.base.control import Choice
    from InquirerPy.separator import Separator
    HAS_INQUIRERPY = True
except ImportError:
    HAS_INQUIRERPY = False


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
    models: list[Model] = field(default_factory=list)

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

    def load_models(self) -> bool:
        """Load available models from this operator."""
        if not self.is_installed:
            return False

        if self.id == "opencode":
            return self._load_opencode_models()
        elif self.id == "aider":
            return self._load_aider_models()
        elif self.id == "gemini":
            return self._load_gemini_models()

        return False

    def _load_opencode_models(self) -> bool:
        """Load models from OpenCode CLI."""
        try:
            result = subprocess.run(
                [self.binary_path, "models"],
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode != 0:
                return False

            # Parse model IDs from output
            model_ids = []
            for line in result.stdout.strip().split("\n"):
                line = line.strip()
                # Skip INFO lines and empty lines
                if not line or line.startswith("INFO"):
                    continue
                # Model ID format: provider/model-name
                if "/" in line:
                    model_ids.append(line)

            # Group by provider and create Model objects
            by_provider = {}
            for model_id in model_ids:
                provider = model_id.split("/")[0]
                if provider not in by_provider:
                    by_provider[provider] = []
                by_provider[provider].append(model_id)

            # Convert to Model objects with nice names
            # NO HARDCODED RECOMMENDATIONS - let the operator decide
            for provider, ids in sorted(by_provider.items()):
                for model_id in sorted(ids):
                    name = self._format_model_name(model_id)
                    desc = self._get_model_description(model_id)
                    # Operator should indicate recommendations in output
                    recommended = False

                    self.models.append(
                        Model(
                            id=model_id,
                            name=name,
                            description=desc,
                            provider=provider,
                            recommended=recommended,
                        )
                    )

            return len(self.models) > 0

        except Exception as e:
            print(f"Error loading OpenCode models: {e}")
            return False

    def _load_aider_models(self) -> bool:
        """Load models from Aider CLI via --list-models."""
        try:
            # Query a few major providers
            all_models = []
            for query in ["claude", "gpt", "gemini", "deepseek", "qwen"]:
                result = subprocess.run(
                    [self.binary_path, "--list-models", query],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )

                if result.returncode == 0:
                    # Parse model IDs from output
                    for line in result.stdout.strip().split("\n"):
                        line = line.strip()
                        # Look for lines starting with "- provider/model"
                        if line.startswith("- ") and "/" in line:
                            model_id = line[2:].strip()  # Remove "- " prefix
                            if model_id not in all_models:
                                all_models.append(model_id)

            # Group by provider
            by_provider = {}
            for model_id in all_models:
                if "/" in model_id:
                    provider = model_id.split("/")[0]
                    if provider not in by_provider:
                        by_provider[provider] = []
                    by_provider[provider].append(model_id)

            # NO HARDCODED RECOMMENDATIONS - operator decides
            for provider, ids in sorted(by_provider.items()):
                for model_id in sorted(ids):
                    name = self._format_model_name(model_id)
                    desc = f"Via OpenRouter"
                    # Operator should indicate recommendations
                    recommended = False

                    self.models.append(
                        Model(
                            id=model_id,
                            name=name,
                            description=desc,
                            provider=provider,
                            recommended=recommended,
                        )
                    )

            return len(self.models) > 0

        except Exception as e:
            print(f"Error loading Aider models: {e}")
            return False

    def _load_gemini_models(self) -> bool:
        """Load models for Gemini CLI."""
        # Gemini CLI uses Google models directly
        # Query a reasonable default list based on Google's API
        try:
            # Try to query from OpenCode if available
            opencode = shutil.which("opencode")
            if opencode:
                result = subprocess.run(
                    [opencode, "models", "google"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )

                if result.returncode == 0:
                    for line in result.stdout.strip().split("\n"):
                        line = line.strip()
                        if line.startswith("google/") and not line.startswith("INFO"):
                            # Remove google/ prefix for Gemini CLI
                            model_id = line.replace("google/", "")
                            name = self._format_model_name(model_id)
                            desc = "Google Gemini model"
                            # NO HARDCODED RECOMMENDATIONS
                            recommended = False

                            self.models.append(
                                Model(
                                    id=model_id,
                                    name=name,
                                    description=desc,
                                    provider="google",
                                    recommended=recommended,
                                )
                            )

            return len(self.models) > 0

        except Exception:
            # Fallback to a minimal list if query fails
            fallback_models = [
                ("gemini-2.5-flash", "Gemini 2.5 Flash", "Latest fast model"),
                ("gemini-2.0-flash", "Gemini 2.0 Flash", "Experimental flash model"),
                ("gemini-1.5-pro", "Gemini 1.5 Pro", "Balanced model"),
                ("gemini-1.5-flash", "Gemini 1.5 Flash", "Fast model"),
            ]

            for model_id, name, desc in fallback_models:
                self.models.append(
                    Model(
                        id=model_id,
                        name=name,
                        description=desc,
                        provider="google",
                        recommended=False,  # NO HARDCODED RECOMMENDATIONS
                    )
                )

            return True

    def _format_model_name(self, model_id: str) -> str:
        """Format a model ID into a human-readable name."""
        # Remove provider prefix
        name = model_id.split("/")[-1]

        # Replace hyphens with spaces and title case
        name = name.replace("-", " ").title()

        # Clean up common patterns
        name = re.sub(r"\d{8}", "", name)  # Remove date stamps
        name = re.sub(r"V\d+:\d+", "", name)  # Remove version suffixes
        name = re.sub(r"@\d+", "", name)  # Remove @ version
        name = re.sub(r"\s+", " ", name).strip()  # Clean up spaces

        return name

    def _get_model_description(self, model_id: str) -> str:
        """Get a description for a model based on its ID."""
        model_lower = model_id.lower()

        # Claude models
        if "claude" in model_lower:
            if "sonnet-4" in model_lower or "sonnet-3-7" in model_lower:
                return "Latest Claude - Balanced performance"
            elif "opus-4" in model_lower:
                return "Most powerful Claude model"
            elif "haiku-4" in model_lower or "haiku-3-5" in model_lower:
                return "Fast & cost-effective"
            elif "sonnet-3-5" in model_lower:
                return "Previous generation - Fast"
            else:
                return "Claude AI model"

        # Gemini models
        elif "gemini" in model_lower:
            if "2.5" in model_lower or "2.0" in model_lower:
                if "flash" in model_lower:
                    return "Latest fast model"
                else:
                    return "Latest balanced model"
            elif "1.5-pro" in model_lower:
                return "Balanced model"
            elif "1.5-flash" in model_lower:
                return "Fast model"
            else:
                return "Google Gemini model"

        # OpenAI models
        elif "gpt" in model_lower:
            if "4o" in model_lower:
                return "Latest OpenAI - Multimodal"
            elif "4-turbo" in model_lower or "4.1" in model_lower:
                return "Fast GPT-4 variant"
            elif "5" in model_lower:
                return "Next-gen reasoning model"
            elif "o1" in model_lower or "o3" in model_lower:
                return "OpenAI reasoning model"
            else:
                return "OpenAI model"

        # DeepSeek
        elif "deepseek" in model_lower:
            return "Specialized coding model"

        # Qwen
        elif "qwen" in model_lower:
            return "Open source coding model"

        return "Available model"


# Define available operators (models will be loaded dynamically)
OPERATORS = [
    Operator(
        id="opencode",
        name="OpenCode",
        binary_name="opencode",
        description="Multi-provider CLI - queries models dynamically",
    ),
    Operator(
        id="aider",
        name="Aider",
        binary_name="aider",
        description="OpenRouter-based CLI - requires OPENROUTER_API_KEY",
    ),
    Operator(
        id="gemini",
        name="Gemini CLI",
        binary_name="gemini",
        description="Google Gemini native CLI",
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
                [operator.binary_path, "auth", "list"],
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
    """Interactive operator selection with InquirerPy."""
    if not HAS_INQUIRERPY:
        print("\n⚠️  InquirerPy not installed. Install with: pip install InquirerPy")
        return None

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

    # Build choices with operator info
    choices = []
    for op in installed:
        auth_status = check_operator_auth(op)
        auth_count = sum(auth_status.values())

        auth_providers = ", ".join([p for p, a in auth_status.items() if a]) if auth_count > 0 else "none"

        display_name = f"{op.name}  •  {op.description}"
        display_name += f"  •  Auth: {auth_providers}"

        choices.append(Choice(
            value=op.id,
            name=display_name
        ))

    try:
        result = inquirer.select(
            message="Select operator:",
            choices=choices,
            pointer="►",
            vi_mode=False,
        ).execute()

        if result:
            # Find selected operator
            selected = next((op for op in installed if op.id == result), None)
            if selected:
                # Load models dynamically
                print(f"\n🔄 Loading available models from {selected.name}...")
                if selected.load_models():
                    print(f"✓ Loaded {len(selected.models)} models\n")
                    return selected
                else:
                    print(f"✗ Failed to load models from {selected.name}")
                    return None

        return None

    except KeyboardInterrupt:
        print("\n✗ Cancelled.")
        return None


def select_model_interactive(operator: Operator) -> Optional[Model]:
    """Interactive model selection for a specific operator with arrow-key navigation."""
    if not operator.models:
        print("\n❌ No models available for this operator.")
        return None

    # Get auth status to show which providers are authenticated
    auth_status = check_operator_auth(operator)

    # Group models by provider
    by_provider = {}
    for model in operator.models:
        provider = model.provider
        if provider not in by_provider:
            by_provider[provider] = []
        by_provider[provider].append(model)

    # Use InquirerPy for modern interactive selection
    if HAS_INQUIRERPY:
        return _select_model_inquirerpy(operator, by_provider, auth_status)
    else:
        print("\n⚠️  InquirerPy not installed. Install with: pip install InquirerPy")
        return None


def _select_model_inquirerpy(
    operator: Operator,
    by_provider: dict,
    auth_status: dict
) -> Optional[Model]:
    """Modern interactive selection using InquirerPy with arrow keys and fuzzy search."""
    print("\n" + "=" * 70)
    print(f"  🤖 MODEL SELECTION - {operator.name}")
    print("=" * 70)
    print(f"\n📋 {len(operator.models)} models available")
    print("   Use ↑↓ arrows, j/k, or type to filter • Enter to select • Ctrl+C to cancel\n")

    # Show warning if some providers not authenticated
    unauth_providers = [p for p, auth in auth_status.items() if not auth]
    if unauth_providers:
        print(f"⚠️  Unauthenticated providers: {', '.join(unauth_providers)}")
        print(f"   Models from these providers may not work.\n")

    # Build choices list with ALL models, grouped by provider
    choices = []
    model_map = {}

    for provider in sorted(by_provider.keys()):
        models = by_provider[provider]
        is_auth = auth_status.get(provider, False)
        auth_symbol = "✓" if is_auth else "✗"

        # Add provider separator
        choices.append(Separator(f"  {auth_symbol} {provider.upper()} ({len(models)} models)"))

        # Add ALL models for this provider
        for model in models:
            # Build display name with proper spacing
            display_name = f"    {model.name}"
            if model.description:
                display_name += f"  •  {model.description}"

            # Create unique value key
            choice_value = f"{provider}::{model.id}"
            model_map[choice_value] = model

            choices.append(Choice(
                value=choice_value,
                name=display_name
            ))

    try:
        result = inquirer.select(
            message="Select a model:",
            choices=choices,
            height="70%",
            pointer="►",
            vi_mode=False,
            keybindings={
                "toggle": [],  # Disable space for toggle (not needed for select)
            },
        ).execute()

        if result and result in model_map:
            selected = model_map[result]
            print(f"\n✓ Selected: {selected.name} ({selected.id})")
            return selected
        return None

    except KeyboardInterrupt:
        print("\n✗ Cancelled.")
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
        updated_bin = False
        updated_model = False

        for i, line in enumerate(lines):
            if line.startswith("NINJA_CODE_BIN="):
                lines[i] = f"NINJA_CODE_BIN={operator.binary_path}"
                updated_bin = True
            elif line.startswith("NINJA_MODEL="):
                lines[i] = f"NINJA_MODEL={model.id}"
                updated_model = True

        if not updated_bin:
            lines.append(f"NINJA_CODE_BIN={operator.binary_path}")
        if not updated_model:
            lines.append(f"NINJA_MODEL={model.id}")

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
            print(
                "   Configuration will be updated, but restart Claude Code"
            )
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
    if model.description:
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
