from __future__ import annotations
import pytest


"""
Unit tests for the validator module.

Tests the is_positive and is_even functions with various inputs including
edge cases, negative numbers, zero, and floating point numbers.
"""



def is_positive(x: int | float) -> bool:
    """Check if a number is positive."""
    return x > 0


def is_even(x: int | float) -> bool:
    """Check if a number is even."""
    return x % 2 == 0


class TestIsPositive:
    """Test suite for the is_positive function."""

    def test_positive_integer(self):
        """Test that positive integers return True."""
        assert is_positive(1) is True
        assert is_positive(5) is True
        assert is_positive(100) is True
        assert is_positive(999999) is True

    def test_negative_integer(self):
        """Test that negative integers return False."""
        assert is_positive(-1) is False
        assert is_positive(-5) is False
        assert is_positive(-100) is False
        assert is_positive(-999999) is False

    def test_zero(self):
        """Test that zero returns False."""
        assert is_positive(0) is False
        assert is_positive(0.0) is False

    def test_positive_float(self):
        """Test that positive floats return True."""
        assert is_positive(0.1) is True
        assert is_positive(2.5) is True
        assert is_positive(3.14159) is True
        assert is_positive(100.5) is True

    def test_negative_float(self):
        """Test that negative floats return False."""
        assert is_positive(-0.1) is False
        assert is_positive(-2.5) is False
        assert is_positive(-3.14159) is False
        assert is_positive(-100.5) is False

    def test_very_small_positive(self):
        """Test that very small positive numbers return True."""
        assert is_positive(0.0001) is True
        assert is_positive(1e-10) is True

    def test_very_small_negative(self):
        """Test that very small negative numbers return False."""
        assert is_positive(-0.0001) is False
        assert is_positive(-1e-10) is False


class TestIsEven:
    """Test suite for the is_even function."""

    def test_even_positive_integer(self):
        """Test that even positive integers return True."""
        assert is_even(0) is True
        assert is_even(2) is True
        assert is_even(4) is True
        assert is_even(100) is True
        assert is_even(1000) is True

    def test_odd_positive_integer(self):
        """Test that odd positive integers return False."""
        assert is_even(1) is False
        assert is_even(3) is False
        assert is_even(5) is False
        assert is_even(99) is False
        assert is_even(1001) is False

    def test_even_negative_integer(self):
        """Test that even negative integers return True."""
        assert is_even(-2) is True
        assert is_even(-4) is True
        assert is_even(-100) is True
        assert is_even(-1000) is True

    def test_odd_negative_integer(self):
        """Test that odd negative integers return False."""
        assert is_even(-1) is False
        assert is_even(-3) is False
        assert is_even(-5) is False
        assert is_even(-99) is False

    def test_zero(self):
        """Test that zero is even."""
        assert is_even(0) is True

    def test_even_float_representing_integer(self):
        """Test that floats representing even integers return True."""
        assert is_even(2.0) is True
        assert is_even(4.0) is True
        assert is_even(-2.0) is True
        assert is_even(0.0) is True
        assert is_even(100.0) is True

    def test_odd_float_representing_integer(self):
        """Test that floats representing odd integers return False."""
        assert is_even(1.0) is False
        assert is_even(3.0) is False
        assert is_even(-3.0) is False
        assert is_even(99.0) is False

    def test_float_with_decimal(self):
        """Test that floats with decimal parts return False."""
        assert is_even(2.5) is False
        assert is_even(3.7) is False
        assert is_even(4.1) is False
        assert is_even(-2.5) is False
        assert is_even(0.5) is False

    def test_large_numbers(self):
        """Test even/odd detection with large numbers."""
        assert is_even(1000000) is True
        assert is_even(1000001) is False
        assert is_even(-1000000) is True
        assert is_even(-1000001) is False


class TestIntegration:
    """Integration tests combining both functions."""

    def test_positive_even_numbers(self):
        """Test numbers that are both positive and even."""
        test_numbers = [2, 4, 6, 8, 10, 100]
        for num in test_numbers:
            assert is_positive(num) is True
            assert is_even(num) is True

    def test_positive_odd_numbers(self):
        """Test numbers that are positive but odd."""
        test_numbers = [1, 3, 5, 7, 9, 99]
        for num in test_numbers:
            assert is_positive(num) is True
            assert is_even(num) is False

    def test_negative_even_numbers(self):
        """Test numbers that are negative and even."""
        test_numbers = [-2, -4, -6, -8, -10]
        for num in test_numbers:
            assert is_positive(num) is False
            assert is_even(num) is True

    def test_negative_odd_numbers(self):
        """Test numbers that are negative and odd."""
        test_numbers = [-1, -3, -5, -7, -9]
        for num in test_numbers:
            assert is_positive(num) is False
            assert is_even(num) is False

    def test_zero_special_case(self):
        """Test zero, which is even but not positive."""
        assert is_positive(0) is False
        assert is_even(0) is True
