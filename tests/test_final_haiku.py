import pytest


"""
Unit tests for the Haiku celebration module.

These tests verify the functionality of the celebrate() function.
"""

import pytest


def celebrate():
    """Return the Haiku celebration message."""
    return "Haiku is the new default!"


pytestmark = pytest.mark.unit


class TestCelebrate:
    """Test suite for the celebrate function."""

    def test_celebrate_returns_correct_message(self):
        """Test that celebrate returns the expected message."""
        result = celebrate()
        assert result == "Haiku is the new default!"

    def test_celebrate_returns_string(self):
        """Test that celebrate returns a string type."""
        result = celebrate()
        assert isinstance(result, str)

    def test_celebrate_not_empty(self):
        """Test that celebrate does not return an empty string."""
        result = celebrate()
        assert len(result) > 0

    def test_celebrate_contains_haiku(self):
        """Test that celebrate message contains 'Haiku'."""
        result = celebrate()
        assert "Haiku" in result

    def test_celebrate_contains_default(self):
        """Test that celebrate message contains 'default'."""
        result = celebrate()
        assert "default" in result

    def test_celebrate_exact_format(self):
        """Test that celebrate returns the exact expected format with exclamation."""
        result = celebrate()
        assert result.endswith("!")
        assert result.startswith("Haiku")

    def test_celebrate_is_deterministic(self):
        """Test that celebrate always returns the same value."""
        result1 = celebrate()
        result2 = celebrate()
        result3 = celebrate()
        assert result1 == result2 == result3

    def test_celebrate_message_length(self):
        """Test that celebrate message has expected length."""
        result = celebrate()
        expected_length = len("Haiku is the new default!")
        assert len(result) == expected_length

    def test_celebrate_no_leading_trailing_whitespace(self):
        """Test that celebrate message has no leading or trailing whitespace."""
        result = celebrate()
        assert result == result.strip()
