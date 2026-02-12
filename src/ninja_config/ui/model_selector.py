"""Model selection UI components.

This module provides functions for configuring models across different
ninja components and task types.
"""

from __future__ import annotations

from InquirerPy import inquirer
from InquirerPy.base.control import Choice
from InquirerPy.separator import Separator

from ninja_common.defaults import OPENROUTER_MODELS, PERPLEXITY_MODELS, ZAI_MODELS
from ninja_config.model_selector import check_provider_auth, get_provider_models


def configure_models(config_manager, config: dict) -> None:
    """Configure models for each module with proper model picker.

    Args:
        config_manager: ConfigManager instance for saving settings.
        config: Current configuration dictionary.
    """
    print("\n" + "=" * 80)
    print("  🤖 MODEL CONFIGURATION")
    print("=" * 80)

    # NOTE: These hardcoded model lists are FALLBACKS ONLY for the legacy configure_models() flow.
    # The recommended flow (configure_coder_models, configure_secretary) uses get_provider_models()
    # to dynamically load models from the actual operators. This function is kept for backwards
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
        current = config.get(key, "Not set")
        print(f"  {desc:25} {current}")

    # Select module to configure
    choices = [
        Choice(
            value=(module, desc, models),
            name=f"{desc:25} [{config.get(f'NINJA_{module.upper()}_MODEL', 'Not set')}]",
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
    # NOTE: ZAI_MODELS is a hardcoded FALLBACK list for the legacy configure_models() flow.
    # The recommended flow (configure_coder_models) uses get_provider_models() for dynamic loading.
    if module == "coder":
        model_choices.append(Separator())
        model_choices.append(Separator("── Z.AI / GLM (OpenCode Native) ──"))
        for model_id, model_name, model_desc in ZAI_MODELS:
            model_choices.append(Choice(value=model_id, name=f"{model_name:25} • {model_desc}"))

    model_choices.append(Separator())
    model_choices.append(Choice(value="__custom__", name="📝 Enter custom model name"))
    model_choices.append(Choice(value=None, name="← Back"))

    current_model = config.get(key, "")
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
        config_manager.set(key, selected_model)
        print(f"\n✅ {desc} model updated to: {selected_model}")
    else:
        print("\n💡 No changes made")


def configure_task_based_models(config_manager, config: dict) -> None:
    """Configure task-based model selection.

    Args:
        config_manager: ConfigManager instance for saving settings.
        config: Current configuration dictionary.
    """
    print("\n" + "=" * 80)
    print("  📊 TASK-BASED MODEL SELECTION")
    print("=" * 80)

    # Show current task models
    task_models = [
        ("NINJA_MODEL_QUICK", "Quick Tasks", "Fast simple tasks", "anthropic/claude-haiku-4.5"),
        (
            "NINJA_MODEL_SEQUENTIAL",
            "Sequential Tasks",
            "Complex multi-step tasks",
            "anthropic/claude-haiku-4.5",
        ),
        (
            "NINJA_MODEL_PARALLEL",
            "Parallel Tasks",
            "High concurrency parallel tasks",
            "anthropic/claude-haiku-4.5",
        ),
    ]

    print("\n📋 Current Task Models:")
    for key, name, _, default in task_models:
        current = config.get(key, default)
        print(f"  {name:20} {current}")

    # Show cost/quality preferences
    prefer_cost = config.get("NINJA_PREFER_COST", "false").lower() == "true"
    prefer_quality = config.get("NINJA_PREFER_QUALITY", "false").lower() == "true"
    preference = "Cost" if prefer_cost else "Quality" if prefer_quality else "Balanced"
    print(f"\n🎯 Current Preference: {preference}")

    # Select what to configure
    choices = [
        Choice(
            value="quick",
            name="⚡ Quick Tasks Model     • Fast simple tasks (default: Claude Haiku 4.5)",
        ),
        Choice(
            value="sequential",
            name="📊 Sequential Model     • Complex multi-step (default: Claude Sonnet 4)",
        ),
        Choice(
            value="parallel",
            name="🔀 Parallel Model       • High concurrency (default: Claude Haiku 4.5)",
        ),
        Separator(),
        Choice(value="preferences", name="🎯 Model Preferences    • Cost vs Quality balance"),
        Separator(),
        Choice(value="reset", name="🔄 Reset to Defaults    • Reset all task models"),
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
        configure_model_preferences(config_manager, config)
    elif selected == "reset":
        reset_task_models(config_manager, config, task_models)
    else:
        configure_single_task_model(config_manager, config, selected, task_models)


def configure_single_task_model(
    config_manager, config: dict, task_type: str, task_models: list
) -> None:
    """Configure a single task model.

    Args:
        config_manager: ConfigManager instance for saving settings.
        config: Current configuration dictionary.
        task_type: Type of task ("quick", "sequential", or "parallel").
        task_models: List of (key, name, desc, default) tuples.
    """
    # Find the task model config
    task_info = None
    for key, name, desc, default in task_models:
        if task_type.lower() in name.lower():
            task_info = (key, name, desc, default)
            break

    if not task_info:
        return

    key, name, desc, default = task_info
    current = config.get(key, default)

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
            ("anthropic/claude-sonnet-4-5", "Claude Sonnet 4.5", "Higher quality (more expensive)"),
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
        Choice(value=model_id, name=f"{name:30} • {desc}") for model_id, name, desc in recommended
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
            config_manager.set(key, custom_model)
            print(f"\n✅ {name} model set to: {custom_model}")
    elif selected:
        config_manager.set(key, selected)
        print(f"\n✅ {name} model set to: {selected}")


def configure_model_preferences(config_manager, config: dict) -> None:
    """Configure cost vs quality preferences.

    Args:
        config_manager: ConfigManager instance for saving settings.
        config: Current configuration dictionary.
    """
    print("\n🎯 Model Preferences")
    print("   This affects automatic model selection recommendations.")

    prefer_cost = config.get("NINJA_PREFER_COST", "false").lower() == "true"
    prefer_quality = config.get("NINJA_PREFER_QUALITY", "false").lower() == "true"

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
        config_manager.set("NINJA_PREFER_COST", "true")
        config_manager.set("NINJA_PREFER_QUALITY", "false")
        print("\n✅ Preference set to: Prefer Cost")
    elif selected == "quality":
        config_manager.set("NINJA_PREFER_COST", "false")
        config_manager.set("NINJA_PREFER_QUALITY", "true")
        print("\n✅ Preference set to: Prefer Quality")
    else:
        config_manager.set("NINJA_PREFER_COST", "false")
        config_manager.set("NINJA_PREFER_QUALITY", "false")
        print("\n✅ Preference set to: Balanced")


def configure_models_with_dynamic_loading(
    config_manager, config: dict, module: str, operator: str = "opencode", provider: str = "openrouter"
) -> None:
    """Configure models with dynamic loading and fuzzy search.

    Fetches models dynamically from the operator's API and provides fuzzy search
    for easy model selection. Particularly useful for OpenRouter with 100+ models.

    Args:
        config_manager: ConfigManager instance for saving settings.
        config: Current configuration dictionary.
        module: Module name (e.g., "coder", "researcher", "secretary").
        operator: Operator to use (e.g., "opencode", "aider", "claude").
        provider: Provider to fetch models from (e.g., "openrouter", "anthropic").
    """
    print("\n" + "=" * 80)
    print(f"  🤖 DYNAMIC MODEL SELECTION - {module.upper()}")
    print("=" * 80)

    # Check provider authentication
    is_authenticated = check_provider_auth(provider) if operator == "opencode" else True
    if not is_authenticated and operator == "opencode":
        print(f"\n⚠️  Provider '{provider}' is not authenticated")
        print(f"   Run 'ninja-config configure' → 'OpenCode Authentication' to set up {provider}")
        should_continue = inquirer.confirm(
            message="Continue anyway? (models may not work)",
            default=False,
        ).execute()
        if not should_continue:
            return

    # Fetch models dynamically
    print(f"\n🔄 Fetching models from {operator}/{provider}...")
    dynamic_models = get_provider_models(operator, provider)

    if not dynamic_models:
        print(f"\n⚠️  Could not fetch models from {operator}/{provider}")
        print("   Falling back to hardcoded model list")

        # Fallback static model lists by provider
        static_model_lists = {
            "openrouter": OPENROUTER_MODELS,
            "anthropic": [
                ("anthropic/claude-sonnet-4-5", "Claude Sonnet 4.5", "Latest Sonnet"),
                ("anthropic/claude-opus-4", "Claude Opus 4", "Most capable"),
                ("anthropic/claude-haiku-4-5", "Claude Haiku 4.5", "Fast and efficient"),
            ],
        }

        static_models = static_model_lists.get(provider)
        if not static_models:
            print("\n❌ No models available")
            return

        # Build choices from static list
        model_choices = []
        for model_id, model_name, model_desc in static_models:
            model_choices.append(Choice(value=model_id, name=f"{model_name:30} • {model_desc}"))
    else:
        print(f"✅ Found {len(dynamic_models)} models")
        print("   Use ↑↓ arrows or type to search • Enter to select • Ctrl+C to cancel\n")

        # Build choices from dynamic models
        model_choices = []
        current_provider = None

        for model in dynamic_models:
            # Add provider separator when provider changes
            model_provider = model.provider
            if model_provider != current_provider:
                if current_provider is not None:
                    model_choices.append(Separator())
                model_choices.append(Separator(f"─── {model_provider.upper()} ───"))
                current_provider = model_provider

            # Build display name
            display_name = f"{model.name:35}"
            if model.description:
                display_name += f" • {model.description}"

            model_choices.append(Choice(value=model.id, name=display_name))

    # Add separator and custom option
    model_choices.append(Separator())
    model_choices.append(Choice(value="__custom__", name="✏️  Enter custom model name"))
    model_choices.append(Choice(value=None, name="← Back"))

    # Get current model
    key = f"NINJA_{module.upper()}_MODEL"
    current_model = config.get(key, "")

    # Show selection dialog with fuzzy search
    selected_model = inquirer.select(
        message=f"Select model for {module}:",
        choices=model_choices,
        pointer="►",
        default=current_model if current_model else None,
        height="70%",
    ).execute()

    if selected_model is None:
        return

    if selected_model == "__custom__":
        # Allow custom model input
        selected_model = inquirer.text(
            message="Enter custom model name:",
            default=current_model,
            instruction="e.g., anthropic/claude-sonnet-4, qwen/qwen-2.5-coder-32b",
        ).execute()

    if selected_model:
        config_manager.set(key, selected_model)
        print(f"\n✅ {module.capitalize()} model updated to: {selected_model}")
    else:
        print("\n💡 No changes made")


def reset_task_models(config_manager, config: dict, task_models: list) -> None:
    """Reset task models to defaults.

    Args:
        config_manager: ConfigManager instance for saving settings.
        config: Current configuration dictionary.
        task_models: List of (key, name, desc, default) tuples.
    """
    confirm = inquirer.confirm(
        message="Reset all task models to defaults?",
        default=False,
    ).execute()

    if confirm:
        for key, name, desc, default in task_models:
            config_manager.set(key, default)
        config_manager.set("NINJA_PREFER_COST", "false")
        config_manager.set("NINJA_PREFER_QUALITY", "false")
        print("\n✅ Task models reset to defaults")
