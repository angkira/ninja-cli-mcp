"""
Unit tests for the cube function.

Tests the cube function with various inputs including positive integers,
negative integers, zero, arithmetic properties, special sequences, and
integration scenarios.
"""

from __future__ import annotations

import pytest


def cube(x: int | float) -> int | float:
    """Calculate the cube of a number."""
    return x**3


class TestPositiveIntegers:
    """Test suite for positive integer inputs."""

    def test_small_positive_integers(self):
        """Test that small positive integers are cubed correctly."""
        assert cube(1) == 1
        assert cube(2) == 8
        assert cube(3) == 27
        assert cube(4) == 64
        assert cube(5) == 125

    def test_medium_positive_integers(self):
        """Test that medium positive integers are cubed correctly."""
        assert cube(10) == 1000
        assert cube(25) == 15625
        assert cube(50) == 125000
        assert cube(100) == 1000000

    def test_large_positive_integers(self):
        """Test that large positive integers are cubed correctly."""
        assert cube(1000) == 1000000000
        assert cube(5000) == 125000000000
        assert cube(10000) == 1000000000000


class TestNegativeIntegers:
    """Test suite for negative integer inputs."""

    def test_small_negative_integers(self):
        """Test that small negative integers are cubed correctly."""
        assert cube(-1) == -1
        assert cube(-2) == -8
        assert cube(-3) == -27
        assert cube(-4) == -64
        assert cube(-5) == -125

    def test_medium_negative_integers(self):
        """Test that medium negative integers are cubed correctly."""
        assert cube(-10) == -1000
        assert cube(-25) == -15625
        assert cube(-50) == -125000
        assert cube(-100) == -1000000

    def test_large_negative_integers(self):
        """Test that large negative integers are cubed correctly."""
        assert cube(-1000) == -1000000000
        assert cube(-5000) == -125000000000
        assert cube(-10000) == -1000000000000


class TestZero:
    """Test suite for zero input."""

    def test_zero(self):
        """Test that zero cubed is zero."""
        assert cube(0) == 0


class TestArithmeticProperties:
    """Test suite for arithmetic properties of the cube function."""

    def test_multiplication_property(self):
        """Test that cube(x) * cube(y) == cube(x * y) for certain cases."""
        assert cube(2) * cube(3) == cube(6)
        assert cube(5) * cube(2) == cube(10)
        assert cube(4) * cube(4) == cube(16)

    def test_negation_property(self):
        """Test that cube(-x) == -cube(x) for all x."""
        assert cube(-2) == -cube(2)
        assert cube(-5) == -cube(5)
        assert cube(-10) == -cube(10)
        assert cube(-100) == -cube(100)

    def test_cube_root_property(self):
        """Test that cube(cuberoot(n)) == n for perfect cubes."""
        assert cube(1) == 1
        assert cube(2) == 8
        assert cube(3) == 27
        assert cube(5) == 125

    def test_power_of_three_property(self):
        """Test that cube(x) equals x raised to the power of 3."""
        for x in [0, 1, 2, 3, 5, 10, -2, -5]:
            assert cube(x) == x**3


class TestSpecialSequences:
    """Test suite for special number sequences."""

    def test_perfect_cubes(self):
        """Test cube function with perfect cubes as inputs."""
        perfect_cubes = [1, 8, 27, 64, 125, 216, 343, 512, 729, 1000]
        for n in perfect_cubes:
            result = cube(n)
            assert result == n**3

    def test_fibonacci_numbers(self):
        """Test cube function with Fibonacci sequence numbers."""
        fibonacci = [0, 1, 1, 2, 3, 5, 8, 13, 21, 34, 55, 89]
        for n in fibonacci:
            result = cube(n)
            assert result == n**3

    def test_prime_numbers(self):
        """Test cube function with prime numbers."""
        primes = [2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31]
        for n in primes:
            result = cube(n)
            assert result == n**3

    def test_palindrome_numbers(self):
        """Test cube function with palindrome numbers."""
        palindromes = [1, 2, 3, 11, 22, 33, 121, 131, 141]
        for n in palindromes:
            result = cube(n)
            assert result == n**3


class TestIntegration:
    """Integration tests combining various scenarios."""

    def test_positive_negative_pairs(self):
        """Test that cube(-x) is the negative of cube(x) for paired numbers."""
        test_pairs = [(1, -1), (2, -2), (10, -10), (100, -100), (5, -5)]
        for positive, negative in test_pairs:
            assert cube(negative) == -cube(positive)

    def test_consecutive_integers(self):
        """Test cube function with sequences of consecutive integers."""
        sequences = [
            [0, 1, 2, 3, 4],
            [10, 11, 12, 13, 14],
            [-3, -2, -1, 0, 1],
        ]
        for seq in sequences:
            for n in seq:
                assert cube(n) == n**3

    def test_powers_of_two(self):
        """Test cube function with powers of 2."""
        powers_of_two = [1, 2, 4, 8, 16, 32, 64, 128]
        for n in powers_of_two:
            result = cube(n)
            assert result == n**3

    def test_mixed_signs(self):
        """Test cube function with mixed positive and negative numbers."""
        test_numbers = [-10, -5, -1, 0, 1, 5, 10]
        for n in test_numbers:
            result = cube(n)
            assert result == n**3

    def test_identity_property(self):
        """Test that cube(1) == 1 and cube(-1) == -1."""
        assert cube(1) == 1
        assert cube(-1) == -1
