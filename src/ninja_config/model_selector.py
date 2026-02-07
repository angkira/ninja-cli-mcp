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
from datetime import datetime, timedelta
from pathlib import Path

from ninja_common.config_manager import ConfigManager


try:
    from InquirerPy import inquirer
    from InquirerPy.base.control import Choice
    from InquirerPy.separator import Separator

    HAS_INQUIRERPY = True
except ImportError:
    HAS_INQUIRERPY = False


# OpenCode provider definitions
OPENCODE_PROVIDERS = [
    ("anthropic", "Anthropic", "Claude models - native API"),
    ("google", "Google", "Gemini models - native API"),
    ("openai", "OpenAI", "GPT models - native API"),
    ("github-copilot", "GitHub Copilot", "Via GitHub OAuth"),
    ("openrouter", "OpenRouter", "Multi-provider API - Qwen, DeepSeek, Llama, etc."),
    ("zai", "Z.ai / Zhipu AI", "GLM models - native Coding Plan API support"),
]


def get_opencode_providers() -> list[tuple[str, str, str]]:
    """Return list of available OpenCode providers.

    Returns:
        List of tuples: (provider_id, display_name, description)
    """
    return OPENCODE_PROVIDERS.copy()


def _get_opencode_auth_file() -> Path:
    """Get the path to OpenCode's auth.json file."""
    return Path.home() / ".local" / "share" / "opencode" / "auth.json"


def check_provider_auth(provider: str) -> bool:
    """Check if a provider is already authenticated in OpenCode.

    Args:
        provider: The provider ID (e.g., 'anthropic', 'openrouter')

    Returns:
        True if the provider has credentials stored, False otherwise
    """
    auth_file = _get_opencode_auth_file()

    if not auth_file.exists():
        return False

    try:
        auth_data = json.loads(auth_file.read_text())
        if provider in auth_data:
            # Check if it has a valid key or token
            provider_auth = auth_data[provider]
            if isinstance(provider_auth, dict):
                return bool(provider_auth.get("key") or provider_auth.get("token"))
        return False
    except (json.JSONDecodeError, OSError):
        return False


def configure_opencode_provider(provider_id: str, api_key: str) -> bool:
    """Configure credentials for an OpenCode provider.

    Reads ~/.local/share/opencode/auth.json, adds or updates the provider
    credentials, and writes back.

    Args:
        provider_id: The provider ID (e.g., 'anthropic', 'openrouter')
        api_key: The API key or token for the provider

    Returns:
        True if configuration was successful, False otherwise
    """
    auth_file = _get_opencode_auth_file()

    # Ensure parent directory exists
    auth_file.parent.mkdir(parents=True, exist_ok=True)

    # Read existing auth data
    auth_data = {}
    if auth_file.exists():
        try:
            auth_data = json.loads(auth_file.read_text())
        except (json.JSONDecodeError, OSError):
            auth_data = {}

    # Configure provider credentials
    if provider_id == "github-copilot":
        # GitHub Copilot uses OAuth
        auth_data[provider_id] = {"type": "oauth", "key": api_key}
    else:
        # All other providers use API keys
        auth_data[provider_id] = {"type": "api", "key": api_key}

    # Write back
    try:
        auth_file.write_text(json.dumps(auth_data, indent=2))
        return True
    except OSError:
        return False


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
    binary_path: str | None = None
    models: list[Model] = field(default_factory=list)
    selected_provider: str | None = None

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

    def _get_model_sort_key(self, model_id: str) -> tuple:
        """Generate sort key to prioritize latest/newest models first."""
        # Priority 1: "latest" versions go first
        has_latest = 1 if "latest" in model_id.lower() else 2

        # Priority 2: Extract date (YYYYMMDD) - newer first
        date_match = re.search(r"(\d{8})", model_id)
        if date_match:
            date_str = date_match.group(1)
            try:
                model_date = datetime.strptime(date_str, "%Y%m%d")
                # Negative timestamp so newer dates come first
                date_priority = -model_date.timestamp()
            except ValueError:
                date_priority = 0
        else:
            date_priority = 0

        # Priority 3: Version number - higher first (4.5 > 4.0 > 3.7)
        version_match = re.search(r"(\d+)[.-](\d+)", model_id)
        if version_match:
            major = int(version_match.group(1))
            minor = int(version_match.group(2))
            version_priority = -(major * 100 + minor)  # Negative for reverse sort
        else:
            version_priority = 0

        # Priority 4: Alphabetical by name
        name_priority = model_id.lower()

        return (has_latest, date_priority, version_priority, name_priority)

    def _is_recent_model(self, model_id: str) -> bool:
        """Check if model is recent enough to show (not ancient garbage)."""
        # Filter out embedding/non-chat models
        if any(x in model_id.lower() for x in ["embedding", "whisper", "tts", "dall-e"]):
            return False

        # Always show "latest" versions (but not if they're old base models)
        if "latest" in model_id.lower():
            # Exclude old model families even with "latest"
            return not any(x in model_id for x in ["claude-3-5", "gpt-4-turbo", "gemini-1"])

        # Parse date from model ID (format: YYYYMMDD or YYYY-MM-DD)
        date_match = re.search(r"(\d{4})[- ]?(\d{2})[- ]?(\d{2})", model_id)
        if date_match:
            date_str = "".join(date_match.groups())  # YYYYMMDD
            try:
                model_date = datetime.strptime(date_str, "%Y%m%d")
                # Only show models from last 12 months
                cutoff_date = datetime.now() - timedelta(days=365)
                return model_date >= cutoff_date
            except ValueError:
                pass

        # Claude: keep 4.x and 3.7+, exclude 3.5 and older
        if "claude" in model_id:
            # Exclude claude-3-5 and older
            if re.search(r"claude-3-[0-5]", model_id):
                return False
            # Keep claude-3-7, claude-4, claude-haiku-4, etc
            if "claude-3-7" in model_id or "claude-4" in model_id:
                return True
            return bool(re.search(r"claude-\w+-4", model_id))

        # GPT: exclude 3.x, basic gpt-4, keep 4o/4.1+/5.x/o1/o3
        if "gpt" in model_id or model_id.startswith("openai/o"):
            # Exclude all gpt-3.x
            if "gpt-3" in model_id:
                return False
            # Exclude basic "gpt-4" without suffix
            if model_id.endswith("/gpt-4"):
                return False
            # Keep gpt-4o, gpt-4.1+, gpt-5.x, o1, o3, o4
            if any(
                x in model_id for x in ["gpt-4o", "gpt-4.1", "gpt-4.2", "gpt-5", "o1", "o3", "o4"]
            ):
                return True
            # Exclude gpt-4-turbo (old)
            if "gpt-4-turbo" in model_id:
                return False
            return False

        # Gemini: keep 2.x and newer only
        if "gemini" in model_id:
            if "gemini-1" in model_id:
                return False
            return bool("gemini-2" in model_id or "gemini-3" in model_id)

        # DeepSeek: keep v3, r1, coder, and recent models
        if "deepseek" in model_id:
            return bool(
                "v3" in model_id
                or "r1" in model_id
                or "coder" in model_id
                or "chat" in model_id
                or "2025" in model_id
                or "2026" in model_id
            )

        # Qwen: keep 2.5 and Qwen3 (qwen3-*)
        if "qwen" in model_id:
            return bool("2.5" in model_id or "qwen3" in model_id or "qwen-3" in model_id)

        # Default: if no rule matched, hide it (be conservative)
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
        elif self.id == "claude":
            return self._load_claude_models()

        return False

    def _load_opencode_models(self) -> bool:
        """Load models from OpenCode CLI."""
        try:
            result = subprocess.run(
                [self.binary_path, "models"],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )

            if result.returncode != 0:
                return False

            # Parse model IDs from output and filter recent ones
            model_ids = []
            for line in result.stdout.strip().split("\n"):
                output_line = line.strip()
                # Skip INFO lines and empty lines
                if not output_line or output_line.startswith("INFO"):
                    continue
                # Model ID format: provider/model-name
                if "/" in output_line:
                    # Filter out ancient models
                    if self._is_recent_model(output_line):
                        model_ids.append(output_line)

            # Group by provider and create Model objects
            by_provider = {}
            for model_id in model_ids:
                provider = model_id.split("/")[0]
                if provider not in by_provider:
                    by_provider[provider] = []
                by_provider[provider].append(model_id)

            # Convert to Model objects with nice names
            # NO HARDCODED RECOMMENDATIONS - let the operator decide
            # Sort models: latest first, then by date (newest first), then by version
            for provider, ids in sorted(by_provider.items()):
                sorted_ids = sorted(ids, key=self._get_model_sort_key)
                for model_id in sorted_ids:
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
        """Load models from Aider CLI via --list-models (OpenRouter provider)."""
        try:
            # Query major providers available via OpenRouter
            all_models = []
            for query in ["claude", "gpt", "gemini", "deepseek", "qwen", "llama", "o1", "o3"]:
                result = subprocess.run(
                    [self.binary_path, "--list-models", query],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    check=False,
                )

                if result.returncode == 0:
                    # Parse model IDs from output and filter recent ones
                    for line in result.stdout.strip().split("\n"):
                        model_line = line.strip()
                        # Look for lines starting with "- provider/model"
                        if model_line.startswith("- ") and "/" in model_line:
                            model_id = model_line[2:].strip()  # Remove "- " prefix
                            # Filter out ancient models
                            if model_id not in all_models and self._is_recent_model(model_id):
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
            # Sort models: latest first, then by date (newest first), then by version
            for provider, ids in sorted(by_provider.items()):
                sorted_ids = sorted(ids, key=self._get_model_sort_key)
                for model_id in sorted_ids:
                    name = self._format_model_name(model_id)
                    desc = "Via OpenRouter"
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
                    check=False,
                )

                if result.returncode == 0:
                    for line in result.stdout.strip().split("\n"):
                        gemini_line = line.strip()
                        if gemini_line.startswith("google/") and not gemini_line.startswith("INFO"):
                            # Remove google/ prefix for Gemini CLI
                            model_id = gemini_line.replace("google/", "")
                            # Filter out ancient models
                            if not self._is_recent_model(model_id):
                                continue
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
            # Fallback to a minimal list if query fails (only recent models)
            fallback_models = [
                ("gemini-2.5-flash", "Gemini 2.5 Flash", "Latest fast model"),
                ("gemini-2.0-flash", "Gemini 2.0 Flash", "Flash model"),
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

    def _load_claude_models(self) -> bool:
        """Load models for Claude Code CLI.

        Claude Code only supports Anthropic models natively.
        """
        # Claude Code uses Anthropic models directly
        claude_models = [
            ("claude-sonnet-4", "Claude Sonnet 4", "Latest Claude - Balanced performance"),
            ("claude-opus-4", "Claude Opus 4", "Most powerful Claude model"),
            ("claude-haiku-4", "Claude Haiku 4", "Fast & cost-effective"),
        ]

        for model_id, name, desc in claude_models:
            self.models.append(
                Model(
                    id=model_id,
                    name=name,
                    description=desc,
                    provider="anthropic",
                    recommended=(model_id == "claude-sonnet-4"),  # Sonnet is recommended
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


def get_provider_models(operator: str, provider: str) -> list[Model]:
    """Get models for a specific provider from an operator.

    For opencode: runs `opencode models {provider}` and parses output.
    Filters to recent/relevant models using existing filtering logic.

    Args:
        operator: The operator ID (e.g., 'opencode')
        provider: The provider ID (e.g., 'anthropic', 'openrouter')

    Returns:
        List of Model objects for the specified provider
    """
    models = []

    if operator != "opencode":
        return models

    # Find opencode binary
    opencode_path = shutil.which("opencode")
    if not opencode_path:
        return models

    try:
        # Run opencode models {provider} to get provider-specific models
        result = subprocess.run(
            [opencode_path, "models", provider],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )

        if result.returncode != 0:
            return models

        # Create a temporary operator instance to use its helper methods
        temp_operator = Operator(
            id="opencode",
            name="OpenCode",
            binary_name="opencode",
            description="temp",
        )

        # Parse model IDs from output
        model_ids = []
        for line in result.stdout.strip().split("\n"):
            output_line = line.strip()
            # Skip INFO lines and empty lines
            if not output_line or output_line.startswith("INFO"):
                continue
            # Model ID format: provider/model-name
            if "/" in output_line:
                # Filter out ancient models using the same logic
                if temp_operator._is_recent_model(output_line):
                    model_ids.append(output_line)

        # Sort models: latest first, then by date (newest first), then by version
        sorted_ids = sorted(model_ids, key=temp_operator._get_model_sort_key)

        # Convert to Model objects
        for model_id in sorted_ids:
            model_provider = model_id.split("/")[0]
            name = temp_operator._format_model_name(model_id)
            desc = temp_operator._get_model_description(model_id)

            models.append(
                Model(
                    id=model_id,
                    name=name,
                    description=desc,
                    provider=model_provider,
                    recommended=False,
                )
            )

    except (subprocess.TimeoutExpired, OSError) as e:
        print(f"Error loading models for provider {provider}: {e}")

    return models


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
    Operator(
        id="claude",
        name="Claude Code",
        binary_name="claude",
        description="Anthropic's official CLI - native Claude integration",
    ),
]


# Claude Code models (Anthropic only)
CLAUDE_CODE_MODELS = [
    ("claude-sonnet-4", "Claude Sonnet 4", "Latest Claude - Balanced performance"),
    ("claude-opus-4", "Claude Opus 4", "Most powerful Claude model"),
    ("claude-haiku-4", "Claude Haiku 4", "Fast & cost-effective"),
]


# Perplexity models for researcher module
PERPLEXITY_MODELS = [
    ("sonar", "Sonar", "Fast search-focused model"),
    ("sonar-pro", "Sonar Pro", "Advanced search with better reasoning"),
    ("sonar-reasoning", "Sonar Reasoning", "Complex reasoning with search"),
]


# Z.ai / Zhipu models (via OpenCode)
ZAI_MODELS = [
    ("glm-4.7", "GLM-4.7", "Complex multi-step tasks - supports Coding Plan API"),
    ("glm-4.6v", "GLM-4.6V", "High concurrency (20 parallel) - best for parallel tasks"),
    ("glm-4.0", "GLM-4.0", "Fast and cost-effective - quick tasks"),
]


# OpenRouter models (for Aider - uses OPENROUTER_API_KEY)
OPENROUTER_MODELS = [
    # Claude models (Anthropic)
    ("anthropic/claude-sonnet-4-5", "Claude Sonnet 4.5", "Latest Claude - Balanced"),
    ("anthropic/claude-opus-4", "Claude Opus 4", "Most powerful Claude"),
    ("anthropic/claude-haiku-4.5", "Claude Haiku 4.5", "Fast & cost-effective"),
    # GPT models (OpenAI)
    ("openai/gpt-4o", "GPT-4o", "OpenAI flagship multimodal"),
    ("openai/gpt-4o-mini", "GPT-4o Mini", "Fast and cheap"),
    ("openai/o1", "O1", "OpenAI reasoning model"),
    ("openai/o3-mini", "O3 Mini", "Latest reasoning model"),
    # Qwen 3 models (Latest generation)
    ("qwen/qwen3-235b-a22b", "Qwen3 235B", "Most powerful Qwen"),
    ("qwen/qwen3-32b", "Qwen3 32B", "Balanced performance"),
    ("qwen/qwen3-14b", "Qwen3 14B", "Good speed/quality"),
    ("qwen/qwen3-8b", "Qwen3 8B", "Fast and capable"),
    # DeepSeek models
    ("deepseek/deepseek-chat", "DeepSeek Chat", "General purpose"),
    ("deepseek/deepseek-coder", "DeepSeek Coder", "Specialized for code"),
    ("deepseek/deepseek-r1", "DeepSeek R1", "Reasoning model"),
    # Google models
    ("google/gemini-2.0-flash", "Gemini 2.0 Flash", "Latest fast model"),
    # Meta Llama models
    ("meta-llama/llama-3.3-70b-instruct", "Llama 3.3 70B", "Latest Llama"),
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
                check=False,
            )
            output = result.stdout.lower()

            auth_status["anthropic"] = "anthropic" in output
            auth_status["google"] = "google" in output
            auth_status["openai"] = "openai" in output
            auth_status["github"] = "github" in output or "copilot" in output
            auth_status["zai"] = "zai" in output or "zhipu" in output
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

    elif operator.id == "claude":
        # Claude Code uses claude auth
        try:
            result = subprocess.run(
                [operator.binary_path, "auth", "status"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            # Claude auth status returns 0 when authenticated
            auth_status["anthropic"] = result.returncode == 0
        except Exception:
            auth_status["anthropic"] = False

    return auth_status


def select_operator_interactive() -> Operator | None:
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

        auth_providers = (
            ", ".join([p for p, a in auth_status.items() if a]) if auth_count > 0 else "none"
        )

        display_name = f"{op.name}  •  {op.description}"
        display_name += f"  •  Auth: {auth_providers}"

        choices.append(Choice(value=op.id, name=display_name))

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


def select_model_interactive(operator: Operator) -> Model | None:
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
    operator: Operator, by_provider: dict, auth_status: dict
) -> Model | None:
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
        print("   Models from these providers may not work.\n")

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

            choices.append(Choice(value=choice_value, name=display_name))

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


def delete_component(component_name: str) -> bool:
    """Delete a component's configuration.

    Args:
        component_name: Component name (e.g., 'ninja-resources', 'ninja-prompts').

    Returns:
        True if successful, False otherwise.
    """
    print(f"\n🗑️  Deleting configuration for {component_name}...")

    config_manager = ConfigManager()
    config = config_manager.read_config()

    # Module-specific environment variable patterns
    module_patterns = {
        "ninja-resources": ["NINJA_RESOURCES_"],
        "ninja-prompts": ["NINJA_PROMPTS_"],
        "ninja-coder": ["NINJA_CODER_", "NINJA_CODE_BIN", "NINJA_MODEL"],
        "ninja-researcher": ["NINJA_RESEARCHER_"],
        "ninja-secretary": ["NINJA_SECRETARY_"],
    }

    patterns = module_patterns.get(component_name, [])
    if not patterns:
        print(f"   ✗ Unknown component: {component_name}")
        return False

    deleted_keys = []
    for key in list(config.keys()):
        for pattern in patterns:
            if key.startswith(pattern):
                config_manager.delete(key)
                deleted_keys.append(key)
                break

    if deleted_keys:
        print(f"   ✓ Deleted {len(deleted_keys)} configuration keys:")
        for key in deleted_keys:
            print(f"      - {key}")
        return True
    else:
        print(f"   ℹ️  No configuration found for {component_name}")
        return True


def get_active_modules() -> set[str]:
    """Get list of active modules from mcp-modules.json.

    Returns:
        Set of module IDs (e.g., {'ninja-coder', 'ninja-researcher'}).
    """
    modules_file = Path(__file__).parent.parent.parent / "config" / "mcp-modules.json"
    if not modules_file.exists():
        return set()

    try:
        with modules_file.open() as f:
            data = json.load(f)
        return set(data.get("modules", {}).keys())
    except Exception:
        return set()


def cleanup_removed_modules(config_manager: ConfigManager) -> list[str]:
    """Remove configuration for modules that no longer exist.

    Args:
        config_manager: ConfigManager instance.

    Returns:
        List of removed module names.
    """
    active_modules = get_active_modules()
    config = config_manager.read_config()

    # Known module prefixes and their environment variable patterns
    module_patterns = {
        "ninja-resources": ["NINJA_RESOURCES_"],
        "ninja-prompts": ["NINJA_PROMPTS_"],
        "ninja-coder": ["NINJA_CODER_", "NINJA_CODE_BIN"],
        "ninja-researcher": ["NINJA_RESEARCHER_"],
        "ninja-secretary": ["NINJA_SECRETARY_"],
    }

    removed = []
    keys_to_delete = []

    for module_id, patterns in module_patterns.items():
        if module_id not in active_modules:
            # Module was removed - delete its config
            for key in config.keys():
                for pattern in patterns:
                    if key.startswith(pattern):
                        keys_to_delete.append(key)
                        if module_id not in removed:
                            removed.append(module_id)

    # Delete the keys
    for key in keys_to_delete:
        config_manager.delete(key)

    return removed


def update_configuration(operator: Operator, model: Model) -> bool:
    """Update ninja-coder configuration with selected operator and model."""
    print("\n" + "=" * 70)
    print("  💾 UPDATING CONFIGURATION")
    print("=" * 70)

    # Update ~/.ninja-mcp.env
    env_file = Path.home() / ".ninja-mcp.env"
    print(f"\n1. Updating {env_file}...")

    try:
        # Use ConfigManager for clean config updates
        config_manager = ConfigManager()

        # Clean up removed modules first
        removed_modules = cleanup_removed_modules(config_manager)
        if removed_modules:
            print(f"   🗑️  Cleaned up removed modules: {', '.join(removed_modules)}")

        # Read config after cleanup
        config = config_manager.read_config()

        # Update all model-related variables with the full model ID
        config["NINJA_CODE_BIN"] = operator.binary_path
        config["NINJA_MODEL"] = model.id
        config["NINJA_CODER_MODEL"] = model.id
        config["NINJA_MODEL_QUICK"] = model.id
        config["NINJA_MODEL_SEQUENTIAL"] = model.id

        # Write back (updates both regular and export lines)
        config_manager.write_config(config)
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
            check=False,
        )
        if result.returncode == 0:
            print("   ⚠️  Claude Code is running!")
            print("   Configuration will be updated, but restart Claude Code")
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
