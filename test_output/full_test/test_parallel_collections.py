"""
Parallel Test 3: Collections utilities module.
This is an independent task that doesn't depend on other parallel tasks.
"""

from typing import Any


def flatten(nested_list: list[Any]) -> list[Any]:
    """Flatten a nested list."""
    result = []
    for item in nested_list:
        if isinstance(item, list):
            result.extend(flatten(item))
        else:
            result.append(item)
    return result


def remove_duplicates(items: list[Any]) -> list[Any]:
    """Remove duplicates while preserving order."""
    seen = set()
    result = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


def find_max(items: list[int | float]) -> int | float:
    """Find the maximum value in a list."""
    if not items:
        raise ValueError("Cannot find max of empty list")
    return max(items)


def find_min(items: list[int | float]) -> int | float:
    """Find the minimum value in a list."""
    if not items:
        raise ValueError("Cannot find min of empty list")
    return min(items)


def sum_list(items: list[int | float]) -> int | float:
    """Sum all items in a list."""
    return sum(items)


if __name__ == "__main__":
    print(f"flatten([[1, 2], [3, [4, 5]]]) = {flatten([[1, 2], [3, [4, 5]]])}")
    print(f"remove_duplicates([1, 2, 2, 3, 3, 3]) = {remove_duplicates([1, 2, 2, 3, 3, 3])}")
    print(f"max([3, 1, 4, 1, 5]) = {find_max([3, 1, 4, 1, 5])}")
    print(f"min([3, 1, 4, 1, 5]) = {find_min([3, 1, 4, 1, 5])}")
    print(f"sum([1, 2, 3, 4, 5]) = {sum_list([1, 2, 3, 4, 5])}")
