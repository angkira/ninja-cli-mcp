"""
CLI strategy pattern infrastructure for ninja-coder.

This package provides the abstraction layer for supporting multiple CLI tools
(Aider, OpenCode, etc.) through a strategy pattern.
"""

from ninja_coder.strategies.base import (
    CLICapabilities,
    CLICommandResult,
    CLIStrategy,
    ParsedResult,
)
from ninja_coder.strategies.registry import CLIStrategyRegistry


__all__ = [
    "CLICapabilities",
    "CLICommandResult",
    "CLIStrategy",
    "CLIStrategyRegistry",
    "ParsedResult",
]
