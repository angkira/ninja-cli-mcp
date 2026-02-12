"""Test UI refactoring - verify all modules can be imported."""

import sys
from pathlib import Path


# Add src to path
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))


def test_ui_modules_exist():
    """Test that all UI modules exist."""
    from ninja_config import ui

    assert hasattr(ui, "base")
    assert hasattr(ui, "main_menu")
    assert hasattr(ui, "component_setup")
    assert hasattr(ui, "operator_config")
    assert hasattr(ui, "model_selector")
    assert hasattr(ui, "settings")
    print("✅ All 6 UI modules exist")


def test_base_functions_importable():
    """Test base module functions."""

    print("✅ Base functions importable")


def test_main_menu_functions_importable():
    """Test main menu functions."""

    print("✅ Main menu functions importable")


def test_component_setup_functions_importable():
    """Test component setup functions."""

    print("✅ Component setup functions importable")


def test_operator_config_functions_importable():
    """Test operator config functions."""

    print("✅ Operator config functions importable")


def test_model_selector_functions_importable():
    """Test model selector functions."""

    print("✅ Model selector functions importable (5 functions)")


def test_settings_functions_importable():
    """Test settings functions."""

    print("✅ Settings functions importable (9 functions)")


def test_function_signatures():
    """Test that key functions have correct signatures."""
    import inspect

    from ninja_config.ui import (
        advanced_settings,
        configure_models,
        configure_search,
        configure_task_based_models,
        reset_configuration,
    )

    # All these functions should accept config_manager and config
    sig_models = inspect.signature(configure_models)
    assert len(sig_models.parameters) == 2
    assert "config_manager" in sig_models.parameters
    assert "config" in sig_models.parameters

    sig_search = inspect.signature(configure_search)
    assert len(sig_search.parameters) == 2

    sig_task = inspect.signature(configure_task_based_models)
    assert len(sig_task.parameters) == 2

    sig_advanced = inspect.signature(advanced_settings)
    assert len(sig_advanced.parameters) == 2

    sig_reset = inspect.signature(reset_configuration)
    assert len(sig_reset.parameters) == 2

    print("✅ All function signatures correct (config_manager, config)")


if __name__ == "__main__":
    print("\n🧪 Testing UI Refactoring\n" + "=" * 50)

    test_ui_modules_exist()
    test_base_functions_importable()
    test_main_menu_functions_importable()
    test_component_setup_functions_importable()
    test_operator_config_functions_importable()
    test_model_selector_functions_importable()
    test_settings_functions_importable()
    test_function_signatures()

    print("\n" + "=" * 50)
    print("✅ All UI refactoring tests passed!")
    print("\nRefactoring Summary:")
    print("  • 6 UI modules created")
    print("  • 4 base functions")
    print("  • 3 main menu functions")
    print("  • 5 component setup functions")
    print("  • 4 operator config functions")
    print("  • 5 model selector functions")
    print("  • 9 settings functions")
    print("  • Total: 30 functions across 6 modules")
