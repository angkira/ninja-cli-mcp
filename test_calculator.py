"""
Calculator module with basic arithmetic operations.

This module provides simple mathematical functions with type hints and comprehensive docstrings.
"""



def add(a: int | float, b: int | float) -> int | float:
    """
    Add two numbers together.

    Args:
        a: The first number to add (int or float).
        b: The second number to add (int or float).

    Returns:
        The sum of a and b. Returns an int if both inputs are ints,
        otherwise returns a float.

    Examples:
        >>> add(2, 3)
        5
        >>> add(2.5, 3.7)
        6.2
        >>> add(-1, 5)
        4
        >>> add(0, 0)
        0
    """
    return a + b


def multiply(a: int | float, b: int | float) -> int | float:
    """
    Multiply two numbers together.

    Args:
        a: The first number to multiply (int or float).
        b: The second number to multiply (int or float).

    Returns:
        The product of a and b. Returns an int if both inputs are ints,
        otherwise returns a float.

    Examples:
        >>> multiply(2, 3)
        6
        >>> multiply(2.5, 4)
        10.0
        >>> multiply(-3, 5)
        -15
        >>> multiply(0, 100)
        0
    """
    return a * b
