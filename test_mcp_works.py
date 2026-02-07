"""
MCP verification module with simple test functions.

This module provides basic functions to verify that the Ninja MCP system is working correctly.
"""


def hello_world() -> str:
    """
    Return a greeting message confirming MCP is working.

    Returns:
        A string message "Ninja MCP is working!".

    Examples:
        >>> hello_world()
        'Ninja MCP is working!'
    """
    return "Ninja MCP is working!"


def square(x: int) -> int:
    """
    Calculate the square of an integer.

    Args:
        x: The integer to square.

    Returns:
        The square of x (x * x).

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
    return x * x
