"""
Unit tests for CLI strategy base classes.
"""

import unittest
from pathlib import Path
from typing import Any

from src.ninja_coder.strategies.base import (
    CLICapabilities,
    CLICommandResult,
    ParsedResult,
)


class TestCLICapabilities(unittest.TestCase):
    """Test CLICapabilities dataclass."""
    
    def test_creation(self) -> None:
        """Test creating CLICapabilities instance."""
        capabilities = CLICapabilities(
            supports_streaming=True,
            supports_file_context=True,
            supports_model_routing=False,
            supports_native_zai=True,
            max_context_files=10,
            preferred_task_types=["parallel", "sequential"],
        )
        
        self.assertTrue(capabilities.supports_streaming)
        self.assertTrue(capabilities.supports_file_context)
        self.assertFalse(capabilities.supports_model_routing)
        self.assertTrue(capabilities.supports_native_zai)
        self.assertEqual(capabilities.max_context_files, 10)
        self.assertEqual(capabilities.preferred_task_types, ["parallel", "sequential"])


class TestCLICommandResult(unittest.TestCase):
    """Test CLICommandResult dataclass."""
    
    def test_creation(self) -> None:
        """Test creating CLICommandResult instance."""
        result = CLICommandResult(
            command=["aider", "--help"],
            env={"PATH": "/usr/bin"},
            working_dir=Path("/tmp"),
            metadata={"version": "1.0"},
        )
        
        self.assertEqual(result.command, ["aider", "--help"])
        self.assertEqual(result.env, {"PATH": "/usr/bin"})
        self.assertEqual(result.working_dir, Path("/tmp"))
        self.assertEqual(result.metadata, {"version": "1.0"})


class TestParsedResult(unittest.TestCase):
    """Test ParsedResult dataclass."""
    
    def test_creation(self) -> None:
        """Test creating ParsedResult instance."""
        parsed = ParsedResult(
            success=True,
            summary="Task completed successfully",
            notes="No issues encountered",
            touched_paths=["file1.py", "file2.py"],
            retryable_error=False,
        )
        
        self.assertTrue(parsed.success)
        self.assertEqual(parsed.summary, "Task completed successfully")
        self.assertEqual(parsed.notes, "No issues encountered")
        self.assertEqual(parsed.touched_paths, ["file1.py", "file2.py"])
        self.assertFalse(parsed.retryable_error)


# Mock strategy implementation for testing the protocol
class MockStrategy:
    """Mock implementation of CLIStrategy for testing."""
    
    @property
    def name(self) -> str:
        return "mock"
    
    @property
    def capabilities(self) -> CLICapabilities:
        return CLICapabilities(
            supports_streaming=True,
            supports_file_context=True,
            supports_model_routing=True,
            supports_native_zai=False,
            max_context_files=5,
            preferred_task_types=["quick"],
        )
    
    def build_command(
        self,
        prompt: str,
        repo_root: str,
        file_paths: list[str] | None = None,
        model: str | None = None,
        additional_flags: dict[str, Any] | None = None,
    ) -> CLICommandResult:
        command = ["mock-cli", prompt]
        if file_paths:
            command.extend(file_paths)
        return CLICommandResult(
            command=command,
            env={},
            working_dir=Path(repo_root),
            metadata={},
        )
    
    def parse_output(self, stdout: str, stderr: str, exit_code: int) -> ParsedResult:
        return ParsedResult(
            success=exit_code == 0,
            summary=stdout,
            notes=stderr,
            touched_paths=[],
            retryable_error=False,
        )
    
    def should_retry(self, stdout: str, stderr: str, exit_code: int) -> bool:
        return exit_code != 0 and "retry" in stderr
    
    def get_timeout(self, task_type: str) -> int:
        return 300


class TestCLIStrategyProtocol(unittest.TestCase):
    """Test CLIStrategy protocol implementation."""
    
    def setUp(self) -> None:
        """Set up test fixtures."""
        self.strategy = MockStrategy()
    
    def test_name_property(self) -> None:
        """Test name property."""
        self.assertEqual(self.strategy.name, "mock")
    
    def test_capabilities_property(self) -> None:
        """Test capabilities property."""
        capabilities = self.strategy.capabilities
        self.assertTrue(capabilities.supports_streaming)
        self.assertTrue(capabilities.supports_file_context)
        self.assertTrue(capabilities.supports_model_routing)
        self.assertFalse(capabilities.supports_native_zai)
        self.assertEqual(capabilities.max_context_files, 5)
        self.assertEqual(capabilities.preferred_task_types, ["quick"])
    
    def test_build_command(self) -> None:
        """Test build_command method."""
        result = self.strategy.build_command(
            prompt="test task",
            repo_root="/tmp/test",
            file_paths=["file1.py", "file2.py"],
        )
        
        self.assertEqual(result.command, ["mock-cli", "test task", "file1.py", "file2.py"])
        self.assertEqual(result.working_dir, Path("/tmp/test"))
    
    def test_parse_output_success(self) -> None:
        """Test parse_output method with success."""
        result = self.strategy.parse_output("success", "", 0)
        self.assertTrue(result.success)
        self.assertEqual(result.summary, "success")
        self.assertEqual(result.notes, "")
    
    def test_parse_output_failure(self) -> None:
        """Test parse_output method with failure."""
        result = self.strategy.parse_output("", "error", 1)
        self.assertFalse(result.success)
        self.assertEqual(result.summary, "")
        self.assertEqual(result.notes, "error")
    
    def test_should_retry_true(self) -> None:
        """Test should_retry method when retry is needed."""
        result = self.strategy.should_retry("", "retry needed", 1)
        self.assertTrue(result)
    
    def test_should_retry_false(self) -> None:
        """Test should_retry method when retry is not needed."""
        result = self.strategy.should_retry("", "error", 1)
        self.assertFalse(result)
    
    def test_get_timeout(self) -> None:
        """Test get_timeout method."""
        timeout = self.strategy.get_timeout("quick")
        self.assertEqual(timeout, 300)


if __name__ == "__main__":
    unittest.main()
