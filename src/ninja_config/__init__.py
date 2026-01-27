"""
Ninja Config Module - Configuration and model selection tools.
"""

from ninja_config.configurator import run_configurator
from ninja_config.installer import run_installer
from ninja_config.model_selector import (
    detect_operators,
    run_interactive_selector,
    select_model_interactive,
    select_operator_interactive,
)


__all__ = [
    "detect_operators",
    "run_configurator",
    "run_installer",
    "run_interactive_selector",
    "select_model_interactive",
    "select_operator_interactive",
]
