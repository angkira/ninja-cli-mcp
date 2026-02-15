"""
Step 2: String processing utilities that depend on Step 1.
Part of sequential test execution.
"""

from test_sequential_step1 import StringBuffer


class StringProcessor:
    """Process strings with various transformations."""

    def __init__(self, buffer: StringBuffer):
        """Initialize with a string buffer."""
        self.buffer = buffer

    def to_uppercase(self, text: str) -> str:
        """Convert text to uppercase."""
        return text.upper()

    def to_lowercase(self, text: str) -> str:
        """Convert text to lowercase."""
        return text.lower()

    def reverse(self, text: str) -> str:
        """Reverse the text."""
        return text[::-1]

    def count_words(self, text: str) -> int:
        """Count words in text."""
        return len(text.split())

    def process_and_append(self, text: str, operation: str) -> None:
        """Process text and append to buffer."""
        if operation == "upper":
            result = self.to_uppercase(text)
        elif operation == "lower":
            result = self.to_lowercase(text)
        elif operation == "reverse":
            result = self.reverse(text)
        else:
            result = text
        self.buffer.append(result)
