"""
Ninja Config Module - Configuration and model selection tools.
"""

from importlib.metadata import PackageNotFoundError, version


try:
    __version__ = version("ninja-mcp")
except PackageNotFoundError:
    __version__ = "0.0.0-dev"

from ninja_config.configurator import run_configurator
from ninja_config.model_selector import (
    detect_operators,
    run_interactive_selector,
    select_model_interactive,
    select_operator_interactive,
)
from ninja_config.opencode_integration import OpenCodeIntegration
from ninja_config.tui_installer import run_tui_installer


__all__ = [
    "OpenCodeIntegration",
    "detect_operators",
    "run_configurator",
    "run_interactive_selector",
    "run_tui_installer",
    "select_model_interactive",
    "select_operator_interactive",
]
