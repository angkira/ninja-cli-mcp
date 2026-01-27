"""String utility functions for text manipulation.

This module provides utilities for common string operations including:
- Reversing word order in sentences
- Capitalizing sentences
- Removing extra whitespace
- Counting word frequencies
"""

import re
from collections import defaultdict
from typing import Optional


def reverse_words(text: str) -> str:
    """Reverse the order of words in a sentence.

    Takes a string and returns a new string with the words in reverse order,
    preserving the spacing between words.

    Args:
        text: The input string to reverse words in.

    Returns:
        A string with words in reverse order.

    Raises:
        TypeError: If text is not a string.

    Examples:
        >>> reverse_words("Hello World")
        'World Hello'
        >>> reverse_words("one two three")
        'three two one'
        >>> reverse_words("single")
        'single'
        >>> reverse_words("")
        ''
        >>> reverse_words("  spaces  between  ")
        '  between  spaces  '
    """
    if not isinstance(text, str):
        raise TypeError(f"Expected str, got {type(text).__name__}")

    if not text or not text.strip():
        return text

    # Split by whitespace, reverse, and join back
    words = text.split()
    if not words:
        return text

    return " ".join(reversed(words))


def capitalize_sentences(text: str) -> str:
    """Capitalize the first letter of each sentence.

    Detects sentence boundaries (., !, ?) and capitalizes the first letter
    of each sentence. Preserves the rest of the text formatting.

    Args:
        text: The input string to capitalize sentences in.

    Returns:
        A string with the first letter of each sentence capitalized.

    Raises:
        TypeError: If text is not a string.

    Examples:
        >>> capitalize_sentences("hello world. how are you?")
        'Hello world. How are you?'
        >>> capitalize_sentences("first sentence. second one! third?")
        'First sentence. Second one! Third?'
        >>> capitalize_sentences("no punctuation here")
        'No punctuation here'
        >>> capitalize_sentences("")
        ''
        >>> capitalize_sentences("  leading spaces. and more.")
        '  Leading spaces. And more.'
    """
    if not isinstance(text, str):
        raise TypeError(f"Expected str, got {type(text).__name__}")

    if not text or not text.strip():
        return text

    # Split by sentence-ending punctuation while keeping delimiter and spaces
    # Pattern: Split on .!? followed by optional whitespace, capturing both
    sentences = re.split(r"([.!?]\s*)", text)

    result = []
    capitalize_next = True

    for part in sentences:
        if not part:
            continue

        # Check if this part contains sentence-ending punctuation
        if re.match(r"^[.!?]\s*$", part):
            result.append(part)
            capitalize_next = True
        else:
            if capitalize_next:
                # Find the first letter and capitalize it
                for j, char in enumerate(part):
                    if char.isalpha():
                        part = part[:j] + char.upper() + part[j + 1 :]
                        capitalize_next = False
                        break
            result.append(part)

    return "".join(result)


def remove_extra_spaces(text: str) -> str:
    """Remove extra spaces between words.

    Reduces multiple consecutive spaces to a single space while preserving
    leading and trailing spaces.

    Args:
        text: The input string to remove extra spaces from.

    Returns:
        A string with extra spaces removed between words.

    Raises:
        TypeError: If text is not a string.

    Examples:
        >>> remove_extra_spaces("hello  world")
        'hello world'
        >>> remove_extra_spaces("one   two    three")
        'one two three'
        >>> remove_extra_spaces("  leading and trailing  ")
        '  leading and trailing  '
        >>> remove_extra_spaces("")
        ''
        >>> remove_extra_spaces("   ")
        '   '
    """
    if not isinstance(text, str):
        raise TypeError(f"Expected str, got {type(text).__name__}")

    if not text:
        return text

    # Split by whitespace and join with single space
    # But preserve leading/trailing spaces
    leading_spaces = len(text) - len(text.lstrip())
    trailing_spaces = len(text) - len(text.rstrip())

    # Get the trimmed text
    trimmed = text.strip()

    if not trimmed:
        # All spaces, return as is
        return text

    # Remove extra spaces in the middle
    cleaned = " ".join(trimmed.split())

    # Restore leading and trailing spaces
    return " " * leading_spaces + cleaned + " " * trailing_spaces


def count_words(text: str) -> dict[str, int]:
    """Count the frequency of each word in the text.

    Returns a dictionary mapping each word (case-insensitive) to its
    frequency in the text. Words are defined as sequences of alphanumeric
    characters.

    Args:
        text: The input string to count words in.

    Returns:
        A dictionary with words as keys and their frequencies as values.
        Returns an empty dictionary for empty or None input.

    Raises:
        TypeError: If text is not a string or None.

    Examples:
        >>> count_words("hello world hello")
        {'hello': 2, 'world': 1}
        >>> count_words("The cat and the dog")
        {'the': 2, 'cat': 1, 'and': 1, 'dog': 1}
        >>> count_words("")
        {}
        >>> count_words("Hello, World! Hello.")
        {'hello': 2, 'world': 1}
    """
    if text is None:
        return {}

    if not isinstance(text, str):
        raise TypeError(f"Expected str or None, got {type(text).__name__}")

    if not text or not text.strip():
        return {}

    # Extract words (alphanumeric sequences) and convert to lowercase
    words = re.findall(r"\b\w+\b", text.lower())

    # Count frequencies
    word_count: dict[str, int] = defaultdict(int)
    for word in words:
        word_count[word] += 1

    return dict(word_count)
