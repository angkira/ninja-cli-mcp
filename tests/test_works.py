"""
Tests for the test_works module.

Tests the square function with various inputs including positive numbers,
zero, negative numbers, and large numbers.
"""



def square(x):
    """Square a number."""
    return x**2


class TestSquareFunction:
    """Test cases for the square function."""

    def test_square_positive_numbers(self):
        """Test square with positive integers."""
        assert square(1) == 1
        assert square(2) == 4
        assert square(5) == 25
        assert square(10) == 100
        assert square(100) == 10000

    def test_square_zero(self):
        """Test square with zero."""
        assert square(0) == 0

    def test_square_negative_numbers(self):
        """Test square with negative integers."""
        assert square(-1) == 1
        assert square(-2) == 4
        assert square(-5) == 25
        assert square(-10) == 100

    def test_square_large_numbers(self):
        """Test square with large integers."""
        assert square(1000) == 1000000
        assert square(10000) == 100000000
        assert square(-1000) == 1000000

    def test_square_type_consistency(self):
        """Test that square returns int for int inputs."""
        result = square(5)
        assert isinstance(result, int)

    def test_square_edge_cases(self):
        """Test square with edge cases."""
        # Test with maximum single-digit number
        assert square(9) == 81
        # Test with negative single-digit
        assert square(-9) == 81
