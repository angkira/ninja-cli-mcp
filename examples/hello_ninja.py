#!/usr/bin/env python3
"""
Simple Fibonacci calculator demonstration script.

This script calculates and displays Fibonacci numbers using an iterative approach
for better efficiency with larger numbers.
"""


def fibonacci(n: int) -> int:
    """
    Calculate the nth Fibonacci number using an iterative approach.

    Args:
        n: The position in the Fibonacci sequence (0-indexed)

    Returns:
        The nth Fibonacci number

    Examples:
        >>> fibonacci(0)
        0
        >>> fibonacci(5)
        5
        >>> fibonacci(10)
        55
    """
    if n < 0:
        raise ValueError("n must be non-negative")

    if n <= 1:
        return n

    a, b = 0, 1
    for _ in range(2, n + 1):
        a, b = b, a + b

    return b


def main() -> None:
    """Calculate and print Fibonacci numbers from 0 to 10."""
    print("Fibonacci numbers from 0 to 10:")
    print("-" * 30)

    for i in range(11):
        result = fibonacci(i)
        print(f"F({i:2d}) = {result:3d}")


if __name__ == "__main__":
    main()
