"""
Ninja Config Module - Configuration and model selection tools.

Heavy submodules (configurator/InquirerPy, tui_installer, model_selector)
are imported lazily via PEP 562 so that lightweight entry points
(e.g. ``ninja_config.modern_tui`` first paint) don't pay ~200ms of
import cost up front. ``from ninja_config import <name>`` keeps working.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version
from typing import TYPE_CHECKING, Any


try:
    __version__ = version("ninja-mcp")
except PackageNotFoundError:
    __version__ = "0.0.0-dev"

if TYPE_CHECKING:
    from ninja_config.configurator import run_configurator
    from ninja_config.model_selector import (
        detect_operators,
        run_interactive_selector,
        select_model_interactive,
        select_operator_interactive,
    )
    from ninja_config.opencode_integration import OpenCodeIntegration
    from ninja_config.tui_installer import run_tui_installer

_LAZY_ATTRS: dict[str, str] = {
    "run_configurator": "ninja_config.configurator",
    "detect_operators": "ninja_config.model_selector",
    "run_interactive_selector": "ninja_config.model_selector",
    "select_model_interactive": "ninja_config.model_selector",
    "select_operator_interactive": "ninja_config.model_selector",
    "OpenCodeIntegration": "ninja_config.opencode_integration",
    "run_tui_installer": "ninja_config.tui_installer",
}


def __getattr__(name: str) -> Any:
    if name in _LAZY_ATTRS:
        import importlib

        module = importlib.import_module(_LAZY_ATTRS[name])
        value = getattr(module, name)
        globals()[name] = value  # Cache for subsequent lookups.
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "OpenCodeIntegration",
    "detect_operators",
    "run_configurator",
    "run_interactive_selector",
    "run_tui_installer",
    "select_model_interactive",
    "select_operator_interactive",
]
