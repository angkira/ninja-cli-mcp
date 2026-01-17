"""
Unit tests for CLI strategy registry.
"""

import unittest
from typing import Type
from unittest.mock import Mock

from src.ninja_coder.models import NinjaConfig
from src.ninja_coder.strategies.base import CLIStrategy
from src.ninja_coder.strategies.registry import CLIStrategyRegistry, GenericStrategy


class TestGenericStrategy(unittest.TestCase):
    """Test GenericStrategy class."""
    
    def setUp(self) -> None:
        """Set up test fixtures."""
        self.strategy = GenericStrategy()
    
    def test_name_property(self) -> None:
        """Test name property."""
        self.assertEqual(self.strategy.name, "generic")
    
    def test_capabilities_property(self) -> None:
        """Test capabilities property."""
        capabilities = self.strategy.capabilities
        self.assertFalse(capabilities["supports_streaming"])
        self.assertFalse(capabilities["supports_file_context"])
        self.assertFalse(capabilities["supports_model_routing"])
        self.assertFalse(capabilities["supports_native_zai"])
        self.assertEqual(capabilities["max_context_files"], 0)
        self.assertEqual(capabilities["preferred_task_types"], [])
    
    def test_should_retry(self) -> None:
        """Test should_retry method."""
        result = self.strategy.should_retry("", "", 0)
        self.assertFalse(result)
    
    def test_get_timeout(self) -> None:
        """Test get_timeout method."""
        timeout = self.strategy.get_timeout("any")
        self.assertEqual(timeout, 300)
    
    def test_build_command_raises(self) -> None:
        """Test that build_command raises NotImplementedError."""
        with self.assertRaises(NotImplementedError):
            self.strategy.build_command("", "")
    
    def test_parse_output_raises(self) -> None:
        """Test that parse_output raises NotImplementedError."""
        with self.assertRaises(NotImplementedError):
            self.strategy.parse_output("", "", 0)


class TestCLIStrategyRegistry(unittest.TestCase):
    """Test CLIStrategyRegistry class."""
    
    def setUp(self) -> None:
        """Set up test fixtures."""
        # Clear registry between tests
        CLIStrategyRegistry._strategies = {}
    
    def test_register(self) -> None:
        """Test register method."""
        mock_strategy: Type[CLIStrategy] = Mock()
        CLIStrategyRegistry.register("test", mock_strategy)
        self.assertIn("test", CLIStrategyRegistry._strategies)
        self.assertEqual(CLIStrategyRegistry._strategies["test"], mock_strategy)
    
    def test_list_strategies(self) -> None:
        """Test list_strategies method."""
        self.assertEqual(CLIStrategyRegistry.list_strategies(), [])
        
        mock_strategy: Type[CLIStrategy] = Mock()
        CLIStrategyRegistry.register("test1", mock_strategy)
        CLIStrategyRegistry.register("test2", mock_strategy)
        
        strategies = CLIStrategyRegistry.list_strategies()
        self.assertIn("test1", strategies)
        self.assertIn("test2", strategies)
        self.assertEqual(len(strategies), 2)
    
    def test_get_strategy_aider(self) -> None:
        """Test get_strategy method with aider binary."""
        mock_strategy_class = Mock()
        mock_strategy_instance = Mock()
        mock_strategy_class.return_value = mock_strategy_instance
        CLIStrategyRegistry.register("aider", mock_strategy_class)
        
        config = NinjaConfig()  # type: ignore
        strategy = CLIStrategyRegistry.get_strategy("/usr/bin/aider", config)
        
        # Should return the registered aider strategy
        mock_strategy_class.assert_called_once_with(config)
        self.assertEqual(strategy, mock_strategy_instance)
    
    def test_get_strategy_opencode(self) -> None:
        """Test get_strategy method with opencode binary."""
        mock_strategy_class = Mock()
        mock_strategy_instance = Mock()
        mock_strategy_class.return_value = mock_strategy_instance
        CLIStrategyRegistry.register("opencode", mock_strategy_class)
        
        config = NinjaConfig()  # type: ignore
        strategy = CLIStrategyRegistry.get_strategy("/usr/local/bin/opencode", config)
        
        # Should return the registered opencode strategy
        mock_strategy_class.assert_called_once_with(config)
        self.assertEqual(strategy, mock_strategy_instance)
    
    def test_get_strategy_fallback(self) -> None:
        """Test get_strategy method with unknown binary."""
        config = NinjaConfig()  # type: ignore
        strategy = CLIStrategyRegistry.get_strategy("/usr/bin/unknown", config)
        
        # Should return generic strategy
        self.assertIsInstance(strategy, GenericStrategy)
    
    def test_get_strategy_partial_match(self) -> None:
        """Test get_strategy method with partial name match."""
        mock_strategy_class = Mock()
        mock_strategy_instance = Mock()
        mock_strategy_class.return_value = mock_strategy_instance
        CLIStrategyRegistry.register("aider", mock_strategy_class)
        
        config = NinjaConfig()  # type: ignore
        strategy = CLIStrategyRegistry.get_strategy("/usr/bin/my-aider-tool", config)
        
        # Should match aider in the name
        mock_strategy_class.assert_called_once_with(config)
        self.assertEqual(strategy, mock_strategy_instance)


if __name__ == "__main__":
    unittest.main()
