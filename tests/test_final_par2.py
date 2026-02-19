import pytest


"""
Tests for the test_final_par2 module.

Tests the div() function with various inputs and edge cases.
"""

import pytest


def div(a, b):
    """Divide two numbers."""
    return a / b


class TestDiv:
    """Test cases for the div() function."""

    def test_div_basic_integers(self):
        """Test division with basic integer inputs."""
        assert div(10, 2) == 5.0
        assert div(20, 4) == 5.0
        assert div(100, 10) == 10.0

    def test_div_fractional_result(self):
        """Test division that results in a fraction."""
        assert div(5, 2) == 2.5
        assert div(7, 2) == 3.5
        assert div(1, 2) == 0.5
        assert div(3, 4) == 0.75

    def test_div_negative_numbers(self):
        """Test division with negative numbers."""
        assert div(-10, 2) == -5.0
        assert div(10, -2) == -5.0
        assert div(-10, -2) == 5.0
        assert div(-5, 2) == -2.5

    def test_div_zero_dividend(self):
        """Test division with zero as the dividend."""
        assert div(0, 5) == 0.0
        assert div(0, 1) == 0.0
        assert div(0, -5) == -0.0

    def test_div_zero_divisor_raises_error(self):
        """Test that division by zero raises ZeroDivisionError."""
        with pytest.raises(ZeroDivisionError):
            div(10, 0)

    def test_div_float_inputs(self):
        """Test division with float inputs."""
        assert div(10.0, 2.0) == 5.0
        assert div(5.5, 2.0) == 2.75
        assert div(10, 2.5) == 4.0
        assert div(3.14, 2.0) == 1.57

    def test_div_mixed_int_float(self):
        """Test division with mixed integer and float inputs."""
        assert div(10, 2.0) == 5.0
        assert div(10.0, 2) == 5.0
        assert div(7, 2.0) == 3.5
        assert div(7.0, 2) == 3.5

    def test_div_large_numbers(self):
        """Test division with large numbers."""
        assert div(1000000, 10) == 100000.0
        assert div(999999999, 9) == 111111111.0

    def test_div_small_numbers(self):
        """Test division with small fractional numbers."""
        assert abs(div(0.1, 0.2) - 0.5) < 1e-10
        assert abs(div(0.01, 0.1) - 0.1) < 1e-10

    def test_div_result_type(self):
        """Test that division returns a float."""
        result = div(10, 2)
        assert isinstance(result, float)

    def test_div_positive_result(self):
        """Test division that results in a positive number."""
        assert div(10, 2) == 5.0
        assert div(-10, -2) == 5.0

    def test_div_negative_result(self):
        """Test division that results in a negative number."""
        assert div(10, -2) == -5.0
        assert div(-10, 2) == -5.0

    def test_div_identity(self):
        """Test division of a number by itself."""
        assert div(5, 5) == 1.0
        assert div(-3, -3) == 1.0
        assert div(2.5, 2.5) == 1.0

    def test_div_by_one(self):
        """Test division by one."""
        assert div(10, 1) == 10.0
        assert div(-5, 1) == -5.0
        assert div(3.14, 1) == 3.14

    def test_div_by_negative_one(self):
        """Test division by negative one."""
        assert div(10, -1) == -10.0
        assert div(-5, -1) == 5.0
        assert div(3.14, -1) == -3.14
