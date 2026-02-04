"""
CLI strategy registry for dynamic strategy selection.

This module provides a registry pattern for managing and selecting
appropriate CLI strategies based on binary path.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, ClassVar

from ninja_coder.strategies.aider_strategy import AiderStrategy
from ninja_coder.strategies.claude_strategy import ClaudeStrategy
from ninja_coder.strategies.gemini_strategy import GeminiStrategy
from ninja_coder.strategies.opencode_strategy import OpenCodeStrategy


if TYPE_CHECKING:
    from ninja_coder.driver import NinjaConfig
    from ninja_coder.strategies.base import CLIStrategy


class CLIStrategyRegistry:
    """Registry for CLI strategy selection.

    This class maintains a registry of available CLI strategies and provides
    methods to register new strategies and select appropriate strategy
    based on binary path.
    """

    _strategies: ClassVar[dict[str, type[CLIStrategy]]] = {
        "aider": AiderStrategy,
        "opencode": OpenCodeStrategy,
        "gemini": GeminiStrategy,
        "claude": ClaudeStrategy,
    }

    @classmethod
    def register(cls, name: str, strategy_class: type[CLIStrategy]) -> None:
        """Register a new CLI strategy.

        Args:
            name: Strategy name (e.g., 'aider', 'opencode', 'gemini').
            strategy_class: Class implementing CLIStrategy protocol.
        """
        cls._strategies[name] = strategy_class

    @classmethod
    def get_strategy(cls, bin_path: str, config: NinjaConfig) -> CLIStrategy:
        """Get appropriate strategy based on binary name.

        Detects CLI type from binary path and returns an instance
        of corresponding strategy.

        Args:
            bin_path: Path to the CLI binary.
            config: Ninja configuration object.

        Returns:
            Instance of appropriate CLI strategy.

        Raises:
            ValueError: If no suitable strategy is found.
        """
        bin_name = Path(bin_path).name.lower()

        # Detection logic based on binary name
        if "aider" in bin_name:
            strategy_name = "aider"
        elif "opencode" in bin_name or "opencode-cli" in bin_name:
            strategy_name = "opencode"
        elif "gemini" in bin_name:
            strategy_name = "gemini"
        elif "claude" in bin_name:
            strategy_name = "claude"
        else:
            # No specific strategy found - return generic if available
            raise ValueError(
                f"No suitable strategy found for binary '{bin_name}'. "
                f"Supported strategies: {', '.join(cls._strategies.keys())}. "
                f"Ensure your CLI binary name contains one of these identifiers."
            )

        # Get strategy class from registry
        strategy_class = cls._strategies.get(strategy_name)

        if strategy_class is None:
            raise ValueError(
                f"Strategy '{strategy_name}' is not registered. "
                f"Available strategies: {', '.join(cls._strategies.keys())}"
            )

        # Instantiate and return strategy
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
