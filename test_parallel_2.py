int, float], b: Union[int, float]) -> Union[int, float]:
    "
    Subtract two numbers.

    Args:
        a: The first number (int or float).
        b: The second number to subtract (int or float).

    Returns:
        The difference of a - b. Returns an int if both inputs are ints,
        otherwise returns a float.

    Examples:
        >>> sub(5, 3)
        2
        >>> sub(10.5, 3.2)
        7.3
        >>> sub(-1, 5)
        -6
        >>> sub(0, 0)
        0
    "
    return a - b