"""
Test module for utils.py functions.
Tests is_even and is_odd functions with various inputs.
"""

from utils import is_even, is_odd


def test_is_even():
    """Test that is_even function works correctly."""
    # Test even numbers (should return True)
    assert is_even(0) is True
    assert is_even(2) is True
    assert is_even(4) is True
    assert is_even(100) is True
    assert is_even(-2) is True
    assert is_even(-4) is True

    # Test odd numbers (should return False)
    assert is_even(1) is False
    assert is_even(3) is False
    assert is_even(5) is False
    assert is_even(99) is False
    assert is_even(-1) is False
    assert is_even(-3) is False


def test_is_odd():
    """Test that is_odd function works correctly."""
    # Test odd numbers (should return True)
    assert is_odd(1) is True
    assert is_odd(3) is True
    assert is_odd(5) is True
    assert is_odd(99) is True
    assert is_odd(-1) is True
    assert is_odd(-3) is True

    # Test even numbers (should return False)
    assert is_odd(0) is False
    assert is_odd(2) is False
    assert is_odd(4) is False
    assert is_odd(100) is False
    assert is_odd(-2) is False
    assert is_odd(-4) is False


if __name__ == "__main__":
    test_is_even()
    test_is_odd()
    print("All tests passed!")
