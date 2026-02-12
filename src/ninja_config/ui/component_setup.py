"""Component setup flows for coder and secretary modules.

This module handles component-specific configuration wizards including
operator selection, provider configuration, and model selection.
"""

try:
    from InquirerPy import inquirer
    from InquirerPy.base.control import Choice
    from InquirerPy.separator import Separator

    HAS_INQUIRERPY = True
except ImportError:
    HAS_INQUIRERPY = False

from ninja_common.config_manager import ConfigManager
from ninja_config.model_selector import get_provider_models
from ninja_config.ui.base import detect_installed_tools
from ninja_config.ui.operator_config import select_opencode_provider


def run_coder_setup_flow(config_manager: ConfigManager, config: dict[str, str]) -> None:
    """Run complete coder setup flow: operator -> provider -> models.

    Args:
        config_manager: Configuration manager instance
        config: Current configuration dictionary
    """
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

    tools = detect_installed_tools()

    operator_info = {
        "opencode": ("OpenCode", "Multi-provider CLI (75+ LLMs)"),
        "aider": ("Aider", "OpenRouter-based CLI"),
        "claude": ("Claude Code", "Anthropic's official CLI"),
        "gemini": ("Gemini CLI", "Google native CLI"),
    }

    if not tools:
        print("\n⚠️  No operators detected!")
        print("   Install at least one operator:")
        print("     • OpenCode: https://opencode.dev/download")
        print("     • Aider: uv tool install aider-chat")
        print("     • Claude Code: https://claude.ai/download")
        print("     • Gemini CLI: npm install -g @google/generative-ai-cli")
        return

    current_operator = config.get("NINJA_CODE_BIN", "Not set")
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

    config_manager.set("NINJA_CODE_BIN", selected_operator)
    config["NINJA_CODE_BIN"] = selected_operator
    print(f"\n✅ Operator set to: {selected_operator}")

    # Step 2: Provider Selection (for OpenCode)
    selected_provider = None
    if selected_operator == "opencode":
        selected_provider = select_opencode_provider(config_manager, config)
        if not selected_provider:
            print("\n💡 No provider selected, using default")
    elif selected_operator == "claude":
        selected_provider = "anthropic"
        config_manager.set("NINJA_CODER_PROVIDER", "anthropic")
        config["NINJA_CODER_PROVIDER"] = "anthropic"
    elif selected_operator == "aider":
        selected_provider = "openrouter"
        config_manager.set("NINJA_CODER_PROVIDER", "openrouter")
        config["NINJA_CODER_PROVIDER"] = "openrouter"
    elif selected_operator == "gemini":
        selected_provider = "google"
        config_manager.set("NINJA_CODER_PROVIDER", "google")
        config["NINJA_CODER_PROVIDER"] = "google"

    # Step 3: Model Configuration
    configure_coder_models(config_manager, config, selected_operator, selected_provider)

    print("\n" + "=" * 80)
    print("  ✅ CODER SETUP COMPLETE")
    print("=" * 80)
    print(f"\n   Operator:  {selected_operator}")
    print(f"   Provider:  {selected_provider or 'default'}")
    print(f"   Model:     {config.get('NINJA_CODER_MODEL', 'Not set')}")
    print(f"   Quick:     {config.get('NINJA_MODEL_QUICK', 'Same as regular')}")
    print(f"   Heavy:     {config.get('NINJA_MODEL_SEQUENTIAL', 'Not set')}")


def configure_coder_models(
    config_manager: ConfigManager,
    config: dict[str, str],
    operator: str | None = None,
    provider: str | None = None,
) -> None:
    """Configure coder models: regular, quick, and heavy task models.

    Args:
        config_manager: Configuration manager instance
        config: Current configuration dictionary
        operator: Operator ID (default: from config)
        provider: Provider ID (default: from config)
    """
    print("\n" + "-" * 50)
    print("  STEP 3: MODEL CONFIGURATION")
    print("-" * 50)

    # Get operator and provider if not provided
    if not operator:
        operator = config.get("NINJA_CODE_BIN", "opencode")
    if not provider:
        provider = config.get("NINJA_CODER_PROVIDER", "anthropic")

    # Fetch available models from the operator/provider
    print(f"\n🔄 Loading models from {operator}/{provider}...")

    try:
        models = get_provider_models(operator, provider)
    except Exception as e:
        print(f"\n⚠️  Failed to load models: {e}")
        print("   Using fallback model list")
        models = get_fallback_models(provider)

    if not models:
        print("\n⚠️  No models available, using fallback list")
        models = get_fallback_models(provider)

    print(f"   Found {len(models)} models\n")

    # Group models by provider with separators
    model_choices = build_model_choices(models, provider)

    # 3a: Regular model (NINJA_CODER_MODEL)
    print("\n📦 Regular Model (NINJA_CODER_MODEL)")
    print("   Main model for standard coding tasks")

    current_model = config.get("NINJA_CODER_MODEL", "")

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
        config_manager.set("NINJA_CODER_MODEL", selected_model)
        config["NINJA_CODER_MODEL"] = selected_model
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
            config_manager.set("NINJA_MODEL_QUICK", selected_model)
            config["NINJA_MODEL_QUICK"] = selected_model
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
            config_manager.set("NINJA_MODEL_QUICK", quick_model)
            config["NINJA_MODEL_QUICK"] = quick_model
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
        config_manager.set("NINJA_MODEL_SEQUENTIAL", heavy_model)
        config["NINJA_MODEL_SEQUENTIAL"] = heavy_model
        print(f"   ✅ Heavy model: {heavy_model}")


def configure_secretary(config_manager: ConfigManager, config: dict[str, str]) -> None:
    """Configure secretary module with its own operator and model.

    Args:
        config_manager: Configuration manager instance
        config: Current configuration dictionary
    """
    print("\n" + "=" * 80)
    print("  📋 SECRETARY SETUP")
    print("=" * 80)
    print("\n  Secretary module handles documentation and analysis tasks.")
    print("  It can use a different operator/model than the coder module.")

    # Current secretary config
    current_operator = config.get("NINJA_SECRETARY_OPERATOR", "")
    current_model = config.get("NINJA_SECRETARY_MODEL", "")
    coder_operator = config.get("NINJA_CODE_BIN", "opencode")
    coder_model = config.get("NINJA_CODER_MODEL", "")

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
        config_manager.set("NINJA_SECRETARY_OPERATOR", coder_operator)
        config["NINJA_SECRETARY_OPERATOR"] = coder_operator
        print(f"\n✅ Secretary operator: {coder_operator} (same as coder)")
    else:
        # Select different operator for secretary
        tools = detect_installed_tools()
        operator_info = {
            "opencode": ("OpenCode", "Multi-provider CLI"),
            "aider": ("Aider", "OpenRouter-based CLI"),
            "claude": ("Claude Code", "Anthropic's official CLI"),
            "gemini": ("Gemini CLI", "Google native CLI"),
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
            config_manager.set("NINJA_SECRETARY_OPERATOR", secretary_operator)
            config["NINJA_SECRETARY_OPERATOR"] = secretary_operator
            print(f"\n✅ Secretary operator: {secretary_operator}")
        else:
            secretary_operator = current_operator or coder_operator

    # Get provider for secretary operator
    secretary_provider = None
    if secretary_operator == "opencode":
        secretary_provider = config.get("NINJA_CODER_PROVIDER", "anthropic")
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
        config_manager.set("NINJA_SECRETARY_MODEL", coder_model)
        config["NINJA_SECRETARY_MODEL"] = coder_model
        print(f"\n✅ Secretary model: {coder_model} (same as coder)")
    else:
        # Fetch available models
        print(f"\n🔄 Loading models from {secretary_operator}/{secretary_provider}...")

        try:
            models = get_provider_models(secretary_operator, secretary_provider)
        except Exception as e:
            print(f"\n⚠️  Failed to load models: {e}")
            models = get_fallback_models(secretary_provider)

        if not models:
            models = get_fallback_models(secretary_provider)

        print(f"   Found {len(models)} models\n")

        model_choices = build_model_choices(models, secretary_provider)
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
            config_manager.set("NINJA_SECRETARY_MODEL", secretary_model)
            config["NINJA_SECRETARY_MODEL"] = secretary_model
            print(f"\n✅ Secretary model: {secretary_model}")

    print("\n" + "=" * 80)
    print("  ✅ SECRETARY SETUP COMPLETE")
    print("=" * 80)
    print(f"\n   Operator: {config.get('NINJA_SECRETARY_OPERATOR', coder_operator)}")
    print(f"   Model:    {config.get('NINJA_SECRETARY_MODEL', 'Not set')}")


def build_model_choices(models: list, current_provider: str | None = None) -> list:
    """Build model choices grouped by provider with separators.

    Args:
        models: List of Model objects or tuples
        current_provider: Current provider to prioritize (optional)

    Returns:
        List of Choice and Separator objects for InquirerPy
    """
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
            provider = model_id.split("/")[0] if "/" in model_id else current_provider or "unknown"
        else:
            continue

        if not provider:
            provider = model_id.split("/")[0] if "/" in model_id else current_provider or "unknown"

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


def get_fallback_models(provider: str | None = None) -> list:
    """Get fallback model list when dynamic loading fails.

    Args:
        provider: Provider ID to get models for (optional)

    Returns:
        List of model tuples (id, name, description)
    """
    from ninja_common.defaults import PROVIDER_MODELS

    if provider and provider in PROVIDER_MODELS:
        return list(PROVIDER_MODELS[provider])

    # Default fallback - mix of top models
    return [
        ("anthropic/claude-haiku-4.5", "Claude Haiku 4.5", "Fast & cost-effective"),
        ("anthropic/claude-sonnet-4-5", "Claude Sonnet 4.5", "Latest Claude - Balanced"),
        ("openai/gpt-4o", "GPT-4o", "OpenAI flagship multimodal"),
        ("google/gemini-2.0-flash", "Gemini 2.0 Flash", "Latest fast model"),
    ]
