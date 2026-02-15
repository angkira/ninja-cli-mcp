"""
Math utility module demonstrating simple task functionality.
Tests basic math operations with type hints and docstrings.
"""

from typing import List


def factorial(n: int) -> int:
    """
    Calculate the factorial of n.

    Args:
        n: A non-negative integer

    Returns:
        The factorial of n

    Raises:
        ValueError: If n is negative
    """
    if n < 0:
        raise ValueError("Factorial not defined for negative numbers")
    if n == 0 or n == 1:
        return 1
    return n * factorial(n - 1)


def fibonacci(n: int) -> int:
    """
    Calculate the nth Fibonacci number.

    Args:
        n: A non-negative integer representing position in sequence

    Returns:
        The nth Fibonacci number

    Raises:
        ValueError: If n is negative
    """
    if n < 0:
        raise ValueError("Fibonacci index must be non-negative")
    if n == 0:
        return 0
    if n == 1:
        return 1
    return fibonacci(n - 1) + fibonacci(n - 2)


def is_prime(n: int) -> bool:
    """
    Check if a number is prime.

    Args:
        n: An integer to check for primality

    Returns:
        True if n is prime, False otherwise
    """
    if n < 2:
        return False
    if n == 2:
        return True
    if n % 2 == 0:
        return False
    for i in range(3, int(n**0.5) + 1, 2):
        if n % i == 0:
            return False
    return True


def get_primes(limit: int) -> List[int]:
    """
    Get all prime numbers up to a limit.

    Args:
        limit: Upper bound for prime search

    Returns:
        List of all prime numbers up to and including limit
    """
    return [n for n in range(2, limit + 1) if is_prime(n)]


if __name__ == "__main__":
    # Test functions
    print("Testing factorial(5):", factorial(5))
    print("Testing fibonacci(7):", fibonacci(7))
    print("Testing is_prime(17):", is_prime(17))
    print("Testing get_primes(20):", get_primes(20))
