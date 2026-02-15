"""Module containing a recursive factorial implementation with tests."""


def factorial(n: int) -> int:
    """Calculate the factorial of a non-negative integer using recursion.

    Args:
        n: A non-negative integer

    Returns:
        The factorial of n (n!)

    Raises:
        ValueError: If n is negative
        TypeError: If n is not an integer

    Examples:
        >>> factorial(0)
        1
        >>> factorial(5)
        120
        >>> factorial(1)
        1
    """
    if not isinstance(n, int):
        raise TypeError("n must be an integer")

    if n < 0:
        raise ValueError("n must be non-negative")

    # Base case
    if n == 0 or n == 1:
        return 1

    # Recursive case
    return n * factorial(n - 1)


def test_factorial():
    """Test cases for the factorial function."""
    # Test base cases
    assert factorial(0) == 1, "Factorial of 0 should be 1"
    assert factorial(1) == 1, "Factorial of 1 should be 1"

    # Test positive integers
    assert factorial(5) == 120, "Factorial of 5 should be 120"
    assert factorial(3) == 6, "Factorial of 3 should be 6"
    assert factorial(10) == 3628800, "Factorial of 10 should be 3628800"

    # Test error cases
    try:
        factorial(-1)
        assert False, "Should raise ValueError for negative input"
    except ValueError:
        pass  # Expected

    try:
        factorial(3.5)
        assert False, "Should raise TypeError for float input"
    except TypeError:
        pass  # Expected

    try:
        factorial("5")
        assert False, "Should raise TypeError for string input"
    except TypeError:
        pass  # Expected


if __name__ == "__main__":
    test_factorial()
    print("All tests passed!")
    print(f"5! = {factorial(5)}")
