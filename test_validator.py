"""
Validator module for number validation operations.

This module provides validation functions for numbers, using the calculator module
for mathematical operations. Includes type hints and comprehensive docstrings.
"""

from typing import Union
from test_calculator import add, multiply


def is_positive(n: Union[int, float]) -> bool:
    """
    Check if a number is positive (greater than zero).

    Uses the add function from test_calculator to perform the comparison
    by adding the number to itself and checking the result.

    Args:
        n: The number to check (int or float).

    Returns:
        True if the number is positive (n > 0), False otherwise.

    Examples:
        >>> is_positive(5)
        True
        >>> is_positive(-3)
        False
        >>> is_positive(0)
        False
        >>> is_positive(2.5)
        True
        >>> is_positive(-1.5)
        False
    """
    # Using add from test_calculator: if n + n > 0, then n > 0
    # This is true because if n > 0, then 2n > 0
    # If n <= 0, then 2n <= 0
    return add(n, n) > 0


def is_even(n: Union[int, float]) -> bool:
    """
    Check if a number is even.

    Uses the multiply function from test_calculator to determine evenness
    by checking if n/2 multiplied by 2 equals the original number.

    For floating point numbers, this checks if the number represents
    an even integer value (e.g., 4.0 is even, but 4.5 is not).

    Args:
        n: The number to check (int or float).

    Returns:
        True if the number is even, False otherwise.
        For floats, returns True only if the float represents an even integer.

    Examples:
        >>> is_even(4)
        True
        >>> is_even(5)
        False
        >>> is_even(0)
        True
        >>> is_even(-2)
        True
        >>> is_even(-3)
        False
        >>> is_even(4.0)
        True
        >>> is_even(4.5)
        False
    """
    # Using multiply from test_calculator: if (n // 2) * 2 == n, then n is even
    # We need to handle floats carefully - only even if it's a whole number
    if n != int(n):
        # If n has a decimal part, it's not even
        return False

    # Convert to int for modulo operation
    n_int = int(n)
    # Use multiply to check: if n/2 * 2 equals n, it's even
    half = n_int // 2
    return multiply(half, 2) == n_int
