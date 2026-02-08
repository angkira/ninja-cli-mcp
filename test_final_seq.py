"""
Counter module with a simple counter class.

This module provides a Counter class for tracking a count value.
"""


class Counter:
    """
    A simple counter class that tracks a count value.

    Attributes:
        count: The current count value (initialized to 0).

    Examples:
        >>> counter = Counter()
        >>> counter.count
        0
    """

    def __init__(self) -> None:
        """
        Initialize a new Counter with count set to 0.

        The counter starts at 0 and can be modified through its count attribute.
        """
        self.count = 0


if __name__ == "__main__":
    import doctest

    doctest.testmod()
