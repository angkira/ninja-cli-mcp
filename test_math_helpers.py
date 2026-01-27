"""Comprehensive tests for math_helpers module.

Tests cover normal cases, edge cases, and error cases for all functions
in the math_helpers module.
"""

import pytest

from math_helpers import add, multiply


class TestAdd:
    """Tests for add function."""

    def test_add_positive_integers(self) -> None:
        """Test adding two positive integers."""
        assert add(2, 3) == 5
        assert add(10, 20) == 30

    def test_add_negative_integers(self) -> None:
        """Test adding two negative integers."""
        assert add(-5, -10) == -15
        assert add(-2, -3) == -5

    def test_add_mixed_sign_integers(self) -> None:
        """Test adding positive and negative integers."""
        assert add(-5, 10) == 5
        assert add(10, -5) == 5
        assert add(-10, 5) == -5

    def test_add_with_zero(self) -> None:
        """Test adding zero to a number."""
        assert add(0, 0) == 0
        assert add(5, 0) == 5
        assert add(0, 5) == 5
        assert add(-5, 0) == -5

    def test_add_positive_floats(self) -> None:
        """Test adding two positive floats."""
        assert add(2.5, 3.5) == 6.0
        assert add(1.1, 2.2) == pytest.approx(3.3)

    def test_add_negative_floats(self) -> None:
        """Test adding two negative floats."""
        assert add(-2.5, -3.5) == -6.0
        assert add(-1.1, -2.2) == pytest.approx(-3.3)

    def test_add_mixed_sign_floats(self) -> None:
        """Test adding positive and negative floats."""
        assert add(-2.5, 5.0) == 2.5
        assert add(5.0, -2.5) == 2.5

    def test_add_float_and_integer(self) -> None:
        """Test adding a float and an integer."""
        assert add(1.5, 2) == 3.5
        assert add(2, 1.5) == 3.5
        assert add(-1.5, 3) == 1.5

    def test_add_large_numbers(self) -> None:
        """Test adding very large numbers."""
        assert add(1000000, 2000000) == 3000000
        assert add(1e10, 2e10) == 3e10

    def test_add_small_numbers(self) -> None:
        """Test adding very small numbers."""
        assert add(0.001, 0.002) == pytest.approx(0.003)
        assert add(1e-10, 2e-10) == pytest.approx(3e-10)

    def test_add_type_error_none(self) -> None:
        """Test that None input raises TypeError."""
        with pytest.raises(TypeError, match="must be int or float"):
            add(None, 5)  # type: ignore
        with pytest.raises(TypeError, match="must be int or float"):
            add(5, None)  # type: ignore

    def test_add_type_error_string(self) -> None:
        """Test that string input raises TypeError."""
        with pytest.raises(TypeError, match="must be int or float"):
            add("5", 3)  # type: ignore
        with pytest.raises(TypeError, match="must be int or float"):
            add(3, "5")  # type: ignore

    def test_add_type_error_list(self) -> None:
        """Test that list input raises TypeError."""
        with pytest.raises(TypeError, match="must be int or float"):
            add([1, 2], 3)  # type: ignore
        with pytest.raises(TypeError, match="must be int or float"):
            add(3, [1, 2])  # type: ignore

    def test_add_type_error_boolean(self) -> None:
        """Test that boolean input raises TypeError."""
        with pytest.raises(TypeError, match="Boolean arguments are not supported"):
            add(True, 5)  # type: ignore
        with pytest.raises(TypeError, match="Boolean arguments are not supported"):
            add(5, False)  # type: ignore

    def test_add_identity_property(self) -> None:
        """Test the identity property: a + 0 = a."""
        assert add(42, 0) == 42
        assert add(0, 42) == 42

    def test_add_commutative_property(self) -> None:
        """Test the commutative property: a + b = b + a."""
        assert add(3, 5) == add(5, 3)
        assert add(2.5, 3.5) == add(3.5, 2.5)


class TestMultiply:
    """Tests for multiply function."""

    def test_multiply_positive_integers(self) -> None:
        """Test multiplying two positive integers."""
        assert multiply(2, 3) == 6
        assert multiply(10, 20) == 200

    def test_multiply_negative_integers(self) -> None:
        """Test multiplying two negative integers."""
        assert multiply(-5, -10) == 50
        assert multiply(-2, -3) == 6

    def test_multiply_mixed_sign_integers(self) -> None:
        """Test multiplying positive and negative integers."""
        assert multiply(-5, 3) == -15
        assert multiply(5, -3) == -15
        assert multiply(-10, 2) == -20

    def test_multiply_with_zero(self) -> None:
        """Test multiplying by zero."""
        assert multiply(0, 0) == 0
        assert multiply(5, 0) == 0
        assert multiply(0, 5) == 0
        assert multiply(-5, 0) == 0
        assert multiply(0, -5) == 0

    def test_multiply_with_one(self) -> None:
        """Test multiplying by one (identity)."""
        assert multiply(1, 5) == 5
        assert multiply(5, 1) == 5
        assert multiply(1, -5) == -5
        assert multiply(-5, 1) == -5

    def test_multiply_positive_floats(self) -> None:
        """Test multiplying two positive floats."""
        assert multiply(2.5, 4.0) == 10.0
        assert multiply(1.5, 2.0) == 3.0

    def test_multiply_negative_floats(self) -> None:
        """Test multiplying two negative floats."""
        assert multiply(-2.5, -4.0) == 10.0
        assert multiply(-1.5, -2.0) == 3.0

    def test_multiply_mixed_sign_floats(self) -> None:
        """Test multiplying positive and negative floats."""
        assert multiply(-2.5, 4.0) == -10.0
        assert multiply(2.5, -4.0) == -10.0

    def test_multiply_float_and_integer(self) -> None:
        """Test multiplying a float and an integer."""
        assert multiply(2.5, 4) == 10.0
        assert multiply(4, 2.5) == 10.0
        assert multiply(-2.5, 3) == -7.5

    def test_multiply_large_numbers(self) -> None:
        """Test multiplying very large numbers."""
        assert multiply(1000000, 2) == 2000000
        assert multiply(1e5, 1e5) == 1e10

    def test_multiply_small_numbers(self) -> None:
        """Test multiplying very small numbers."""
        assert multiply(0.001, 0.002) == pytest.approx(0.000002)
        assert multiply(1e-5, 2e-5) == pytest.approx(2e-10)

    def test_multiply_fractions(self) -> None:
        """Test multiplying fractional numbers."""
        assert multiply(0.5, 0.5) == 0.25
        assert multiply(0.25, 4) == 1.0

    def test_multiply_type_error_none(self) -> None:
        """Test that None input raises TypeError."""
        with pytest.raises(TypeError, match="must be int or float"):
            multiply(None, 5)  # type: ignore
        with pytest.raises(TypeError, match="must be int or float"):
            multiply(5, None)  # type: ignore

    def test_multiply_type_error_string(self) -> None:
        """Test that string input raises TypeError."""
        with pytest.raises(TypeError, match="must be int or float"):
            multiply("5", 3)  # type: ignore
        with pytest.raises(TypeError, match="must be int or float"):
            multiply(3, "5")  # type: ignore

    def test_multiply_type_error_list(self) -> None:
        """Test that list input raises TypeError."""
        with pytest.raises(TypeError, match="must be int or float"):
            multiply([1, 2], 3)  # type: ignore
        with pytest.raises(TypeError, match="must be int or float"):
            multiply(3, [1, 2])  # type: ignore

    def test_multiply_type_error_boolean(self) -> None:
        """Test that boolean input raises TypeError."""
        with pytest.raises(TypeError, match="Boolean arguments are not supported"):
            multiply(True, 5)  # type: ignore
        with pytest.raises(TypeError, match="Boolean arguments are not supported"):
            multiply(5, False)  # type: ignore

    def test_multiply_identity_property(self) -> None:
        """Test the identity property: a * 1 = a."""
        assert multiply(42, 1) == 42
        assert multiply(1, 42) == 42

    def test_multiply_zero_property(self) -> None:
        """Test the zero property: a * 0 = 0."""
        assert multiply(42, 0) == 0
        assert multiply(0, 42) == 0

    def test_multiply_commutative_property(self) -> None:
        """Test the commutative property: a * b = b * a."""
        assert multiply(3, 5) == multiply(5, 3)
        assert multiply(2.5, 4.0) == multiply(4.0, 2.5)


class TestIntegration:
    """Integration tests combining multiple functions."""

    def test_add_then_multiply(self) -> None:
        """Test adding numbers then multiplying the result."""
        result = add(2, 3)
        final = multiply(result, 4)
        assert final == 20

    def test_multiply_then_add(self) -> None:
        """Test multiplying numbers then adding to the result."""
        result = multiply(3, 4)
        final = add(result, 5)
        assert final == 17

    def test_distributive_property(self) -> None:
        """Test the distributive property: a * (b + c) = a * b + a * c."""
        a, b, c = 2, 3, 4
        left_side = multiply(a, add(b, c))
        right_side = add(multiply(a, b), multiply(a, c))
        assert left_side == right_side

    def test_associative_add(self) -> None:
        """Test the associative property for addition: (a + b) + c = a + (b + c)."""
        a, b, c = 2, 3, 4
        left_side = add(add(a, b), c)
        right_side = add(a, add(b, c))
        assert left_side == right_side

    def test_complex_calculation(self) -> None:
        """Test a complex calculation using multiple operations."""
        # Calculate: (2 + 3) * 4 + (5 * 6)
        step1 = add(2, 3)  # 5
        step2 = multiply(step1, 4)  # 20
        step3 = multiply(5, 6)  # 30
        result = add(step2, step3)  # 50
        assert result == 50

    def test_zero_handling_in_pipeline(self) -> None:
        """Test that zero is handled correctly in a calculation pipeline."""
        result = multiply(add(5, 0), 10)
        assert result == 50

    def test_negative_numbers_pipeline(self) -> None:
        """Test a pipeline with negative numbers."""
        # Calculate: (-5 + 3) * 2
        result = multiply(add(-5, 3), 2)
        assert result == -4

    def test_float_precision_pipeline(self) -> None:
        """Test floating-point precision in a calculation pipeline."""
        # Calculate: (1.5 + 2.5) * 0.5
        result = multiply(add(1.5, 2.5), 0.5)
        assert result == pytest.approx(2.0)
