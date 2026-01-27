"""Mathematical helper functions for basic arithmetic operations.

This module provides utilities for common mathematical operations including:
- Addition of two numbers
- Multiplication of two numbers
"""

from typing import Union


Number = Union[int, float]


def add(a: Number, b: Number) -> Number:
    """Add two numbers together.

    Takes two numbers (int or float) and returns their sum. The return type
    will be float if either input is a float, otherwise int.

    Args:
        a: The first number to add.
        b: The second number to add.

    Returns:
        The sum of a and b.

    Raises:
        TypeError: If either argument is not a number (int or float).

    Examples:
        >>> add(2, 3)
        5
        >>> add(2.5, 3.5)
        6.0
        >>> add(-5, 10)
        5
        >>> add(0, 0)
        0
        >>> add(1.5, 2)
        3.5
    """
    if not isinstance(a, (int, float)):
        raise TypeError(f"First argument must be int or float, got {type(a).__name__}")
    if not isinstance(b, (int, float)):
        raise TypeError(f"Second argument must be int or float, got {type(b).__name__}")

    # Handle boolean type (which is technically a subclass of int in Python)
    if isinstance(a, bool) or isinstance(b, bool):
        raise TypeError("Boolean arguments are not supported")

    return a + b


def multiply(a: Number, b: Number) -> Number:
    """Multiply two numbers together.

    Takes two numbers (int or float) and returns their product. The return type
    will be float if either input is a float, otherwise int.

    Args:
        a: The first number to multiply.
        b: The second number to multiply.

    Returns:
        The product of a and b.

    Raises:
        TypeError: If either argument is not a number (int or float).

    Examples:
        >>> multiply(2, 3)
        6
        >>> multiply(2.5, 4)
        10.0
        >>> multiply(-5, 3)
        -15
        >>> multiply(0, 100)
        0
        >>> multiply(1.5, 2.0)
        3.0
        >>> multiply(-2, -3)
        6
    """
    if not isinstance(a, (int, float)):
        raise TypeError(f"First argument must be int or float, got {type(a).__name__}")
    if not isinstance(b, (int, float)):
        raise TypeError(f"Second argument must be int or float, got {type(b).__name__}")

    # Handle boolean type (which is technically a subclass of int in Python)
    if isinstance(a, bool) or isinstance(b, bool):
        raise TypeError("Boolean arguments are not supported")

    return a * b
