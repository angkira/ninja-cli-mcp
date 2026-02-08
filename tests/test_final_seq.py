"""
Tests for the test_final_seq module.

Tests the Counter class initialization and basic functionality.
"""

from test_final_seq import Counter


class TestCounter:
    """Test cases for the Counter class."""

    def test_counter_initialization(self):
        """Test that Counter initializes with count = 0."""
        counter = Counter()
        assert counter.count == 0

    def test_counter_initialization_multiple_instances(self):
        """Test that multiple Counter instances are independent."""
        counter1 = Counter()
        counter2 = Counter()

        assert counter1.count == 0
        assert counter2.count == 0
        assert counter1 is not counter2

    def test_counter_type(self):
        """Test that count attribute is of type int."""
        counter = Counter()
        assert isinstance(counter.count, int)

    def test_counter_attribute_modification(self):
        """Test that count attribute can be modified."""
        counter = Counter()
        assert counter.count == 0

        counter.count = 5
        assert counter.count == 5

        counter.count = 10
        assert counter.count == 10

    def test_counter_increment(self):
        """Test that increment() increases count by 1."""
        counter = Counter()
        assert counter.count == 0

        counter.increment()
        assert counter.count == 1

    def test_counter_increment_multiple(self):
        """Test that multiple increment() calls work correctly."""
        counter = Counter()
        assert counter.count == 0

        for i in range(5):
            counter.increment()
            assert counter.count == i + 1

        assert counter.count == 5

    def test_counter_increment_from_modified_count(self):
        """Test that increment() works from a modified count value."""
        counter = Counter()
        counter.count = 10
        assert counter.count == 10

        counter.increment()
        assert counter.count == 11

    def test_counter_increment_independent_instances(self):
        """Test that increment() works independently across instances."""
        counter1 = Counter()
        counter2 = Counter()

        counter1.increment()
        counter2.increment()

        assert counter1.count == 1
        assert counter2.count == 1

        counter1.increment()
        assert counter1.count == 2
        assert counter2.count == 1
