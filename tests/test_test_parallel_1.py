def add(a, b):
    """Add two numbers."""
    return a + b


def test_add_positive_numbers():
    assert add(1, 2) == 3
    assert add(3, 4) == 7
    assert add(10, 20) == 30


def test_add_negative_numbers():
    assert add(-1, -2) == -3
    assert add(-5, 5) == 0
    assert add(-10, -20) == -30


def test_add_zero():
    assert add(0, 0) == 0
    assert add(0, 5) == 5
    assert add(5, 0) == 5


def test_add_floats():
    assert add(1.5, 2.5) == 4.0
