"""
Unit tests for the MCP verification module.

These tests verify the functionality of hello_world() and square() functions.
"""

import pytest

# Import the functions from the parent directory
import sys
from pathlib import Path

# Add parent directory to path to import test_mcp_works module
sys.path.insert(0, str(Path(__file__).parent.parent))

from test_mcp_works import hello_world, square


pytestmark = pytest.mark.unit


class TestHelloWorld:
    """Test suite for the hello_world function."""

    def test_hello_world_returns_correct_message(self):
        """Test that hello_world returns the expected message."""
        result = hello_world()
        assert result == "Ninja MCP is working!"

    def test_hello_world_returns_string(self):
        """Test that hello_world returns a string type."""
        result = hello_world()
        assert isinstance(result, str)

    def test_hello_world_not_empty(self):
        """Test that hello_world does not return an empty string."""
        result = hello_world()
        assert len(result) > 0

    def test_hello_world_contains_ninja(self):
        """Test that hello_world message contains 'Ninja'."""
        result = hello_world()
        assert "Ninja" in result

    def test_hello_world_contains_mcp(self):
        """Test that hello_world message contains 'MCP'."""
        result = hello_world()
        assert "MCP" in result


class TestSquare:
    """Test suite for the square function."""

    def test_square_positive_number(self):
        """Test squaring a positive integer."""
        assert square(5) == 25
        assert square(10) == 100
        assert square(1) == 1

    def test_square_negative_number(self):
        """Test squaring a negative integer returns positive result."""
        assert square(-3) == 9
        assert square(-5) == 25
        assert square(-10) == 100

    def test_square_zero(self):
        """Test that squaring zero returns zero."""
        assert square(0) == 0

    def test_square_one(self):
        """Test that squaring one returns one."""
        assert square(1) == 1
        assert square(-1) == 1

    def test_square_large_number(self):
        """Test squaring large numbers."""
        assert square(100) == 10000
        assert square(1000) == 1000000

    def test_square_returns_int(self):
        """Test that square returns an integer type."""
        result = square(5)
        assert isinstance(result, int)

    def test_square_multiple_values(self):
        """Test square with multiple test cases."""
        test_cases = [
            (0, 0),
            (1, 1),
            (2, 4),
            (3, 9),
            (4, 16),
            (5, 25),
            (7, 49),
            (11, 121),
            (-2, 4),
            (-7, 49),
        ]
        for input_val, expected in test_cases:
            assert square(input_val) == expected, f"square({input_val}) should equal {expected}"

    def test_square_always_positive(self):
        """Test that square always returns a non-negative result."""
        for x in range(-10, 11):
            result = square(x)
            assert result >= 0, f"square({x}) should be non-negative, got {result}"

    def test_square_idempotent_for_one_and_zero(self):
        """Test that 0 and 1 are idempotent under square operation."""
        assert square(0) == 0
        assert square(1) == 1
        # Second application
        assert square(square(0)) == 0
        assert square(square(1)) == 1
