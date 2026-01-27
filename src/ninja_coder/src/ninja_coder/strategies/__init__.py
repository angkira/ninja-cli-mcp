"""
Strategy pattern infrastructure for CLI abstraction.

This module provides the base classes and registry for different CLI strategies.
"""

from .base import (
    CLICapabilities,
    CLICommandResult,
    CLIStrategy,
    ParsedResult,
)
from .registry import CLIStrategyRegistry


__all__ = [
    "CLICapabilities",
    "CLICommandResult",
    "CLIStrategy",
    "CLIStrategyRegistry",
    "ParsedResult",
]
