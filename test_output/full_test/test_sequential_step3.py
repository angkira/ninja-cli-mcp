"""
Step 3: Integration tests for sequential steps.
Depends on Steps 1 and 2.
"""

from test_sequential_step1 import StringBuffer
from test_sequential_step2 import StringProcessor


def test_sequential_workflow():
    """Test the complete sequential workflow."""
    buffer = StringBuffer()
    processor = StringProcessor(buffer)

    # Process and append various transformations
    processor.process_and_append("hello", "upper")
    processor.process_and_append(" ", "upper")
    processor.process_and_append("world", "upper")

    result = buffer.get_content()
    assert result == "HELLO WORLD", f"Expected 'HELLO WORLD', got '{result}'"
    assert buffer.length() == len("HELLO WORLD")
    assert processor.count_words("hello world test") == 3


def test_string_buffer():
    """Test string buffer operations."""
    buffer = StringBuffer()
    assert buffer.length() == 0

    buffer.append("test")
    assert buffer.length() == 4
    assert buffer.get_content() == "test"

    buffer.clear()
    assert buffer.length() == 0


def test_string_processor():
    """Test string processor operations."""
    buffer = StringBuffer()
    processor = StringProcessor(buffer)

    assert processor.to_uppercase("hello") == "HELLO"
    assert processor.to_lowercase("HELLO") == "hello"
    assert processor.reverse("hello") == "olleh"
    assert processor.count_words("one two three") == 3


if __name__ == "__main__":
    test_sequential_workflow()
    test_string_buffer()
    test_string_processor()
    print("All sequential tests passed!")
