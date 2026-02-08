"""
Division module with a simple division function.

This module provides a div() function for dividing two numbers.
"""


def div(a, b):
    """
    Divide two numbers.

    Args:
        a: The dividend.
        b: The divisor.

    Returns:
        The result of dividing a by b.

    Raises:
        ZeroDivisionError: If b is zero.

    Examples:
        >>> div(10, 2)
        5.0
        >>> div(5, 2)
        2.5
    """
    return a / b


if __name__ == "__main__":
    import doctest

    doctest.testmod()
