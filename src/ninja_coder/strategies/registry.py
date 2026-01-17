"""
CLI strategy registry for dynamic strategy selection.

This module provides a registry pattern for managing and selecting
appropriate CLI strategies based on the binary path.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Type

from ninja_coder.strategies.aider_strategy import AiderStrategy
from ninja_coder.strategies.base import CLIStrategy
from ninja_coder.strategies.opencode_strategy import OpenCodeStrategy

if TYPE_CHECKING:
    from ninja_coder.driver import NinjaConfig


class CLIStrategyRegistry:
    """Registry for CLI strategy selection.

    This class maintains a registry of available CLI strategies and provides
    methods to register new strategies and select the appropriate strategy
    based on the binary path.
    """

    _strategies: dict[str, Type[CLIStrategy]] = {
        "aider": AiderStrategy,
        "opencode": OpenCodeStrategy,
    }

    @classmethod
    def register(cls, name: str, strategy_class: Type[CLIStrategy]) -> None:
        """Register a new CLI strategy.

        Args:
            name: Strategy name (e.g., 'aider', 'opencode').
            strategy_class: Class implementing the CLIStrategy protocol.
        """
        cls._strategies[name] = strategy_class

    @classmethod
    def get_strategy(cls, bin_path: str, config: NinjaConfig) -> CLIStrategy:
        """Get appropriate strategy based on binary name.

        Detects the CLI type from the binary path and returns an instance
        of the corresponding strategy.

        Args:
            bin_path: Path to the CLI binary.
            config: Ninja configuration object.

        Returns:
            Instance of the appropriate CLI strategy.

        Raises:
            ValueError: If no suitable strategy is found and no fallback is available.
        """
        bin_name = Path(bin_path).name.lower()

        # Detection logic based on binary name
        if "aider" in bin_name:
            strategy_name = "aider"
        elif "opencode" in bin_name or "opencode-cli" in bin_name:
            strategy_name = "opencode"
        else:
            # Fallback to generic strategy (if available)
            strategy_name = "generic"

        # Get strategy class from registry
        strategy_class = cls._strategies.get(strategy_name)

        if strategy_class is None:
            # If no strategy found, try to return a generic fallback
            if "generic" in cls._strategies:
                strategy_class = cls._strategies["generic"]
            else:
                available = ", ".join(cls._strategies.keys())
                raise ValueError(
                    f"No strategy found for binary '{bin_name}'. "
                    f"Available strategies: {available}. "
                    f"Please register a strategy or implement a generic fallback."
                )

        # Instantiate and return the strategy
        return strategy_class(bin_path, config)

    @classmethod
    def list_strategies(cls) -> list[str]:
        """List all registered strategy names.

        Returns:
            List of registered strategy names.
        """
        return list(cls._strategies.keys())

    @classmethod
    def clear(cls) -> None:
        """Clear all registered strategies.

        This is primarily useful for testing to ensure a clean state.
        """
        cls._strategies.clear()
