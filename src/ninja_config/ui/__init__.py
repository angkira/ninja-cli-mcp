"""UI module for ninja-config interactive configurator.

This module provides modular UI components for the configuration system,
separated into focused, single-responsibility modules following hexagonal architecture.

Modules:
    base: Shared UI utilities and helper functions
    main_menu: Main configuration menu and overview
    component_setup: Component-specific setup flows (coder, secretary)
    operator_config: Operator and provider configuration
"""

# Import modules for convenience
from ninja_config.ui import base, component_setup, main_menu, operator_config

# Re-export public interface
from ninja_config.ui.base import (
    check_opencode_auth,
    detect_installed_tools,
    get_masked_value,
    print_header,
)
from ninja_config.ui.component_setup import (
    build_model_choices,
    configure_coder_models,
    configure_secretary,
    get_fallback_models,
    run_coder_setup_flow,
)
from ninja_config.ui.main_menu import (
    show_configuration_overview,
    show_main_menu,
    show_welcome,
)
from ninja_config.ui.operator_config import (
    configure_opencode_auth,
    configure_operators,
    manage_api_keys,
    select_opencode_provider,
)

__all__ = [
    # Modules
    "base",
    "component_setup",
    "main_menu",
    "operator_config",
    # Base functions
    "check_opencode_auth",
    "detect_installed_tools",
    "get_masked_value",
    "print_header",
    # Component setup functions
    "build_model_choices",
    "configure_coder_models",
    "configure_secretary",
    "get_fallback_models",
    "run_coder_setup_flow",
    # Main menu functions
    "show_configuration_overview",
    "show_main_menu",
    "show_welcome",
    # Operator config functions
    "configure_opencode_auth",
    "configure_operators",
    "manage_api_keys",
    "select_opencode_provider",
]
