"""
Simple utility module with a square function.

This module provides basic mathematical operations with type hints and comprehensive docstrings.
"""


def square(n: int) -> int:
    """
    Calculate the square of an integer.

    Args:
        n: The integer to square.

    Returns:
        The square of n (n * n).

    Examples:
        >>> square(5)
        25
        >>> square(-3)
        9
        >>> square(0)
        0
        >>> square(10)
        100
    """
    return n * n
