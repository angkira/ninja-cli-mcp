"""
Strategy pattern infrastructure for CLI abstraction.

This module provides the base classes and registry for different CLI strategies.
"""

from .base import (
    CLIStrategy,
    CLICapabilities,
    CLICommandResult,
    ParsedResult,
)
from .registry import CLIStrategyRegistry

__all__ = [
    "CLIStrategy",
    "CLICapabilities",
    "CLICommandResult",
    "ParsedResult",
    "CLIStrategyRegistry",
]
