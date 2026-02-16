"""
Test module for validators.py functions.
Tests is_positive function with various inputs.
"""

from validators import is_positive


def test_is_positive():
    """Test that is_positive function works correctly."""
    # Test positive numbers (should return True)
    assert is_positive(1) is True
    assert is_positive(5) is True
    assert is_positive(100) is True
    assert is_positive(999999) is True

    # Test negative numbers (should return False)
    assert is_positive(-1) is False
    assert is_positive(-5) is False
    assert is_positive(-100) is False
    assert is_positive(-999999) is False

    # Test zero (should return False)
    assert is_positive(0) is False


if __name__ == "__main__":
    test_is_positive()
    print("All tests passed!")
