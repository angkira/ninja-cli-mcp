"""
Integration test for utils and validators modules.
Tests both modules working together.
"""

from utils import is_even, is_odd
from validators import is_positive


def test_integration():
    """Test that both modules work together correctly."""
    # Test positive even numbers
    assert is_positive(2) is True
    assert is_even(2) is True

    # Test positive odd numbers
    assert is_positive(3) is True
    assert is_odd(3) is True

    # Test negative even numbers
    assert is_positive(-4) is False
    assert is_even(-4) is True

    # Test negative odd numbers
    assert is_positive(-5) is False
    assert is_odd(-5) is True

    # Test zero
    assert is_positive(0) is False
    assert is_even(0) is True
    assert is_odd(0) is False


if __name__ == "__main__":
    test_integration()
    print("Integration tests passed!")
