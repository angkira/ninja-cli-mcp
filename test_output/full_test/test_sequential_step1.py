"""
Step 1: Base data structures for string operations.
Part of sequential test execution.
"""


class StringBuffer:
    """A simple string buffer for accumulating text."""

    def __init__(self):
        """Initialize an empty string buffer."""
        self._content: list[str] = []

    def append(self, text: str) -> None:
        """Append text to the buffer."""
        self._content.append(text)

    def get_content(self) -> str:
        """Get the accumulated content."""
        return "".join(self._content)

    def clear(self) -> None:
        """Clear the buffer."""
        self._content.clear()

    def length(self) -> int:
        """Return the length of accumulated content."""
        return len(self.get_content())
