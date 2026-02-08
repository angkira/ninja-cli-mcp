"""Simple mathematical operations module.

This module provides basic mathematical functions with type hints and comprehensive docstrings.
"""

from typing import Union


def cube(x: int) -> int:
    """
    Calculate the cube of an integer.

    Returns the cube (x raised to the power of 3) of the given integer.

    Args:
        x: The integer to cube.

    Returns:
        The cube of x (x ** 3).

    Examples:
        >>> cube(2)
        8
        >>> cube(3)
        27
        >>> cube(0)
        0
        >>> cube(-2)
        -8
        >>> cube(-3)
        -27
    """
    return x**3
