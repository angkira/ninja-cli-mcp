"""Square function module.

This module provides a square function with type hints and comprehensive docstrings.
"""


def square(n: int) -> int:
    """
    Calculate the square of an integer.

    Returns the square (n raised to the power of 2) of the given integer.

    Args:
        n: The integer to square.

    Returns:
        The square of n (n * n).

    Examples:
        >>> square(2)
        4
        >>> square(3)
        9
        >>> square(0)
        0
        >>> square(-2)
        4
        >>> square(-5)
        25
    """
    return n * n
