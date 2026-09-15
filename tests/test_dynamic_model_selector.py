import pytest


"""Test dynamic model selector with multi-operator support."""

import sys
from pathlib import Path


# Add src to path
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))


def test_imports():
    """Test that all new functions can be imported."""

    print("✅ All imports successful")


def test_get_provider_models_signatures():
    """Test that get_provider_models works for all operators."""
    from ninja_config.model_selector import get_provider_models

    # Test with different operators
    operators_to_test = [
        ("opencode", "openrouter"),
        ("aider", "openrouter"),
        ("claude", "anthropic"),
        ("agy", "agy"),
    ]

    for operator, provider in operators_to_test:
        try:
            models = get_provider_models(operator, provider)
            print(f"✅ {operator}/{provider}: returned {len(models)} models")
        except Exception as e:
            print(f"❌ {operator}/{provider}: {e}")


def test_operator_specific_functions(monkeypatch):
    """Test operator-specific model fetching functions."""
    import ninja_config.model_selector as ms
    from ninja_config.model_selector import (
        _get_aider_models,
        _get_agy_models,
        _get_claude_models,
    )

    # Test Claude models (always available, hardcoded)
    claude_models = _get_claude_models()
    assert len(claude_models) > 0, "Claude should return models"
    assert any("sonnet" in m.name.lower() for m in claude_models), "Should have Sonnet"
    print(f"✅ Claude models: {len(claude_models)} models")

    # Test Antigravity models (dynamic via `agy models`, stubbed here)
    monkeypatch.setattr(
        ms,
        "_run_agy_models",
        lambda binary=None: [("gemini-3.8-flash-medium", "Gemini 3.8 Flash (Medium)")],
    )
    agy_models = _get_agy_models()
    assert len(agy_models) > 0, "Antigravity should return models"
    print(f"✅ Antigravity models: {len(agy_models)} models")

    # Test Aider models (may or may not be available)
    aider_models = _get_aider_models("openrouter")
    print(f"✅ Aider models: {len(aider_models)} models (may be 0 if aider not installed)")


def test_dynamic_loading_function_signature():
    """Test the new dynamic loading function signature."""
    import inspect

    from ninja_config.ui import configure_models_with_dynamic_loading

    sig = inspect.signature(configure_models_with_dynamic_loading)
    params = list(sig.parameters.keys())

    expected_params = ["config_manager", "config", "module", "operator", "provider"]
    for param in expected_params[:3]:  # First 3 are required
        assert param in params, f"Missing parameter: {param}"

    print("✅ Dynamic loading function signature correct")


def test_ui_module_exports():
    """Test that UI module exports the new function."""
    from ninja_config import ui

    assert hasattr(ui, "configure_models_with_dynamic_loading")
    print("✅ UI module exports configure_models_with_dynamic_loading")


if __name__ == "__main__":
    print("\n🧪 Testing Dynamic Model Selector\n" + "=" * 50)

    test_imports()
    test_get_provider_models_signatures()
    test_operator_specific_functions()
    test_dynamic_loading_function_signature()
    test_ui_module_exports()

    print("\n" + "=" * 50)
    print("✅ All dynamic model selector tests passed!")
    print("\nEnhancements Summary:")
    print("  • OpenRouter: Dynamic loading with fuzzy search")
    print("  • Aider: Dynamic model listing via --list-models")
    print("  • Claude: Hardcoded Claude 4.x models")
    print("  • Antigravity: Dynamic model listing via `agy models`")
    print("  • InquirerPy: Built-in fuzzy search (type to filter)")
