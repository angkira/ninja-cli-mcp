"""
Registry for CLI strategies.

Manages registration and retrieval of CLI strategy implementations.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .base import CLIStrategy


if TYPE_CHECKING:
    from ninja_coder.models import NinjaConfig


class GenericStrategy(CLIStrategy):
    """Generic fallback strategy."""

    @property
    def name(self) -> str:
        return "generic"

    @property
    def capabilities(self) -> Any:
        # Return minimal capabilities as placeholder
        return {
            "supports_streaming": False,
            "supports_file_context": False,
            "supports_model_routing": False,
            "supports_native_zai": False,
            "max_context_files": 0,
            "preferred_task_types": [],
        }

    def build_command(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError("Generic strategy cannot build commands")

    def parse_output(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError("Generic strategy cannot parse output")

    def should_retry(self, *args: Any, **kwargs: Any) -> bool:
        return False

    def get_timeout(self, *args: Any, **kwargs: Any) -> int:
        return 300


class CLIStrategyRegistry:
    """
    Registry for CLI strategy implementations.

    Manages registration and retrieval of CLI strategies based on binary detection.
    """

    _strategies: dict[str, type[CLIStrategy]] = {}

    @classmethod
    def register(cls, name: str, strategy_class: type[CLIStrategy]) -> None:
        """
        Register a CLI strategy implementation.

        Args:
            name: Name of the strategy
            strategy_class: The strategy class to register
        """
        cls._strategies[name] = strategy_class

    @classmethod
    def get_strategy(cls, bin_path: str, config: NinjaConfig) -> CLIStrategy:
        """
        Get a strategy based on binary path detection.

        Args:
            bin_path: Path to the CLI binary
            config: Ninja configuration

        Returns:
            Appropriate CLI strategy instance
        """
        # Extract binary name from path
        bin_name = bin_path.split("/")[-1]

        # Try to detect known CLI tools
        if "aider" in bin_name:
            if "aider" in cls._strategies:
                return cls._strategies["aider"](config)
        elif "opencode" in bin_name:
            if "opencode" in cls._strategies:
                return cls._strategies["opencode"](config)

        # Return generic strategy as fallback
        return GenericStrategy()

    @classmethod
    def list_strategies(cls) -> list[str]:
        """
        List all registered strategies.

        Returns:
            List of registered strategy names
        """
        return list(cls._strategies.keys())
