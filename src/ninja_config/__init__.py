"""
Ninja Config Module - Configuration and model selection tools.
"""

from importlib.metadata import PackageNotFoundError, version


try:
    __version__ = version("ninja-mcp")
except PackageNotFoundError:
    __version__ = "0.0.0-dev"

from ninja_config.configurator import run_configurator
from ninja_config.installer import run_installer
from ninja_config.model_selector import (
    detect_operators,
    run_interactive_selector,
    select_model_interactive,
    select_operator_interactive,
)
from ninja_config.opencode_integration import OpenCodeIntegration


__all__ = [
    "OpenCodeIntegration",
    "detect_operators",
    "run_configurator",
    "run_installer",
    "run_interactive_selector",
    "select_model_interactive",
    "select_operator_interactive",
]
