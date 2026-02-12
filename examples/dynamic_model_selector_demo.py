"""Demo: Dynamic Model Selector with Fuzzy Search

This demonstrates the new enhanced model selection functionality:
1. Dynamic loading from operator APIs (OpenCode, Aider, etc.)
2. Fuzzy search for easy model discovery
3. Support for all operators (OpenCode, Aider, Claude, Gemini)
"""

import sys
from pathlib import Path


# Add src to path for demo
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))

from ninja_config.model_selector import get_provider_models


def demo_openrouter_models():
    """Demo: Fetch all OpenRouter models dynamically."""
    print("\n" + "=" * 70)
    print("  🌐 OPENROUTER MODELS (Dynamic Loading)")
    print("=" * 70)

    models = get_provider_models("opencode", "openrouter")
    print(f"\n✅ Fetched {len(models)} models from OpenRouter")

    # Show first 10 models
    print("\nSample models (first 10):")
    for model in models[:10]:
        print(f"  • {model.name:40} ({model.id})")

    # Show by provider
    providers = {}
    for model in models:
        providers.setdefault(model.provider, []).append(model)

    print("\n📊 Models by provider:")
    for provider, provider_models in sorted(providers.items()):
        print(f"  • {provider:20} {len(provider_models)} models")

    return models


def demo_operator_comparison():
    """Demo: Compare model availability across operators."""
    print("\n" + "=" * 70)
    print("  🔍 OPERATOR COMPARISON")
    print("=" * 70)

    operators = [
        ("opencode", "openrouter", "OpenCode + OpenRouter"),
        ("opencode", "anthropic", "OpenCode + Anthropic"),
        ("aider", "openrouter", "Aider + OpenRouter"),
        ("claude", "anthropic", "Claude CLI"),
        ("gemini", "google", "Gemini CLI"),
    ]

    print()
    for operator, provider, name in operators:
        models = get_provider_models(operator, provider)
        print(f"  {name:30} {len(models):3} models")


def demo_fuzzy_search_explanation():
    """Explain how fuzzy search works."""
    print("\n" + "=" * 70)
    print("  ⌨️  FUZZY SEARCH (Built-in InquirerPy)")
    print("=" * 70)

    print("""
The new model selector provides fuzzy search out of the box:

1. When you see the model list, just start typing:
   • Type "son" → filters to "Claude Sonnet", "Qwen", etc.
   • Type "haiku" → shows only Haiku models
   • Type "deepseek" → shows all DeepSeek models

2. Navigation:
   • ↑↓ arrows or j/k to move
   • Enter to select
   • Ctrl+C to cancel

3. For OpenRouter (100+ models):
   • All models loaded dynamically
   • Type to filter instantly
   • No need to scroll through everything

Example usage in code:
    from ninja_config.ui import configure_models_with_dynamic_loading

    # Configure coder with OpenRouter (100+ models, fuzzy search)
    configure_models_with_dynamic_loading(
        config_manager,
        config,
        module="coder",
        operator="opencode",
        provider="openrouter"
    )
""")


def demo_migration_path():
    """Show how to migrate from old to new selector."""
    print("\n" + "=" * 70)
    print("  🔄 MIGRATION GUIDE")
    print("=" * 70)

    print("""
Old way (hardcoded lists):
    from ninja_config.ui import configure_models
    configure_models(config_manager, config)
    # Limited to ~20 hardcoded models

New way (dynamic loading + fuzzy search):
    from ninja_config.ui import configure_models_with_dynamic_loading

    # OpenRouter with all available models
    configure_models_with_dynamic_loading(
        config_manager, config,
        module="coder",
        operator="opencode",
        provider="openrouter"
    )

    # Or use with Aider
    configure_models_with_dynamic_loading(
        config_manager, config,
        module="coder",
        operator="aider",
        provider="openrouter"
    )

    # Or Claude CLI
    configure_models_with_dynamic_loading(
        config_manager, config,
        module="coder",
        operator="claude",
        provider="anthropic"
    )

Benefits:
✅ Always up-to-date (fetches from operator)
✅ Fuzzy search (type to filter)
✅ Supports all operators
✅ Falls back to hardcoded if API fails
""")


if __name__ == "__main__":
    print("\n🚀 Dynamic Model Selector Demo")

    # Run demos
    models = demo_openrouter_models()
    demo_operator_comparison()
    demo_fuzzy_search_explanation()
    demo_migration_path()

    print("\n" + "=" * 70)
    print(f"✅ Demo complete! Found {len(models)} OpenRouter models ready for fuzzy search")
    print("=" * 70 + "\n")
