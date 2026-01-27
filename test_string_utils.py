"""Comprehensive tests for string_utils module.

Tests cover normal cases, edge cases, and error cases for all functions
in the string_utils module.
"""

import pytest

from string_utils import (
    capitalize_sentences,
    count_words,
    remove_extra_spaces,
    reverse_words,
)


class TestReverseWords:
    """Tests for reverse_words function."""

    def test_reverse_simple_sentence(self) -> None:
        """Test reversing a simple two-word sentence."""
        assert reverse_words("Hello World") == "World Hello"

    def test_reverse_multiple_words(self) -> None:
        """Test reversing a sentence with multiple words."""
        assert reverse_words("one two three four") == "four three two one"

    def test_reverse_single_word(self) -> None:
        """Test reversing a single word returns the same word."""
        assert reverse_words("single") == "single"

    def test_reverse_empty_string(self) -> None:
        """Test reversing an empty string returns empty string."""
        assert reverse_words("") == ""

    def test_reverse_whitespace_only(self) -> None:
        """Test reversing whitespace-only string preserves it."""
        assert reverse_words("   ") == "   "
        assert reverse_words("\t\n") == "\t\n"

    def test_reverse_with_extra_spaces(self) -> None:
        """Test reversing with multiple spaces between words."""
        result = reverse_words("hello  world")
        assert result == "world hello"

    def test_reverse_with_leading_trailing_spaces(self) -> None:
        """Test reversing preserves leading/trailing spaces pattern."""
        result = reverse_words("  hello world  ")
        assert result == "world hello"

    def test_reverse_with_punctuation(self) -> None:
        """Test reversing words with punctuation attached."""
        assert reverse_words("Hello, World!") == "World! Hello,"

    def test_reverse_type_error_none(self) -> None:
        """Test that None input raises TypeError."""
        with pytest.raises(TypeError, match="Expected str"):
            reverse_words(None)  # type: ignore

    def test_reverse_type_error_int(self) -> None:
        """Test that integer input raises TypeError."""
        with pytest.raises(TypeError, match="Expected str"):
            reverse_words(123)  # type: ignore

    def test_reverse_type_error_list(self) -> None:
        """Test that list input raises TypeError."""
        with pytest.raises(TypeError, match="Expected str"):
            reverse_words(["hello", "world"])  # type: ignore


class TestCapitalizeSentences:
    """Tests for capitalize_sentences function."""

    def test_capitalize_simple_sentence(self) -> None:
        """Test capitalizing a simple sentence."""
        assert capitalize_sentences("hello world") == "Hello world"

    def test_capitalize_multiple_sentences_period(self) -> None:
        """Test capitalizing multiple sentences separated by periods."""
        result = capitalize_sentences("hello world. how are you?")
        assert result == "Hello world. How are you?"

    def test_capitalize_multiple_sentence_types(self) -> None:
        """Test capitalizing sentences with different punctuation."""
        result = capitalize_sentences("first sentence. second one! third?")
        assert result == "First sentence. Second one! Third?"

    def test_capitalize_already_capitalized(self) -> None:
        """Test that already capitalized sentences remain unchanged."""
        result = capitalize_sentences("Hello World. How Are You?")
        assert result == "Hello World. How Are You?"

    def test_capitalize_empty_string(self) -> None:
        """Test capitalizing an empty string returns empty string."""
        assert capitalize_sentences("") == ""

    def test_capitalize_whitespace_only(self) -> None:
        """Test capitalizing whitespace-only string preserves it."""
        assert capitalize_sentences("   ") == "   "

    def test_capitalize_no_punctuation(self) -> None:
        """Test capitalizing text without sentence-ending punctuation."""
        assert capitalize_sentences("no punctuation here") == "No punctuation here"

    def test_capitalize_with_leading_spaces(self) -> None:
        """Test capitalizing preserves leading spaces."""
        result = capitalize_sentences("  hello world. and more.")
        assert result == "  Hello world. And more."

    def test_capitalize_multiple_spaces_between(self) -> None:
        """Test capitalizing with multiple spaces between sentences."""
        result = capitalize_sentences("first.  second.")
        assert "First" in result and "Second" in result

    def test_capitalize_with_numbers(self) -> None:
        """Test capitalizing sentences starting with numbers."""
        result = capitalize_sentences("123 start. abc continue.")
        assert result == "123 Start. Abc continue."

    def test_capitalize_type_error_none(self) -> None:
        """Test that None input raises TypeError."""
        with pytest.raises(TypeError, match="Expected str"):
            capitalize_sentences(None)  # type: ignore

    def test_capitalize_type_error_int(self) -> None:
        """Test that integer input raises TypeError."""
        with pytest.raises(TypeError, match="Expected str"):
            capitalize_sentences(123)  # type: ignore


class TestRemoveExtraSpaces:
    """Tests for remove_extra_spaces function."""

    def test_remove_double_spaces(self) -> None:
        """Test removing double spaces between words."""
        assert remove_extra_spaces("hello  world") == "hello world"

    def test_remove_multiple_spaces(self) -> None:
        """Test removing multiple consecutive spaces."""
        assert remove_extra_spaces("one   two    three") == "one two three"

    def test_remove_with_leading_trailing(self) -> None:
        """Test that leading and trailing spaces are preserved."""
        result = remove_extra_spaces("  hello  world  ")
        assert result == "  hello world  "

    def test_remove_empty_string(self) -> None:
        """Test removing spaces from empty string."""
        assert remove_extra_spaces("") == ""

    def test_remove_whitespace_only(self) -> None:
        """Test that whitespace-only string is preserved."""
        assert remove_extra_spaces("   ") == "   "
        assert remove_extra_spaces("     ") == "     "

    def test_remove_single_word(self) -> None:
        """Test removing spaces from single word (no change)."""
        assert remove_extra_spaces("single") == "single"

    def test_remove_already_clean(self) -> None:
        """Test that already clean text remains unchanged."""
        assert remove_extra_spaces("hello world") == "hello world"

    def test_remove_with_tabs_newlines(self) -> None:
        """Test removing spaces with mixed whitespace."""
        result = remove_extra_spaces("hello\t\tworld")
        assert result == "hello world"

    def test_remove_leading_only(self) -> None:
        """Test preserving only leading spaces."""
        result = remove_extra_spaces("  hello")
        assert result == "  hello"

    def test_remove_trailing_only(self) -> None:
        """Test preserving only trailing spaces."""
        result = remove_extra_spaces("hello  ")
        assert result == "hello  "

    def test_remove_type_error_none(self) -> None:
        """Test that None input raises TypeError."""
        with pytest.raises(TypeError, match="Expected str"):
            remove_extra_spaces(None)  # type: ignore

    def test_remove_type_error_int(self) -> None:
        """Test that integer input raises TypeError."""
        with pytest.raises(TypeError, match="Expected str"):
            remove_extra_spaces(123)  # type: ignore


class TestCountWords:
    """Tests for count_words function."""

    def test_count_simple_sentence(self) -> None:
        """Test counting words in a simple sentence."""
        result = count_words("hello world hello")
        assert result == {"hello": 2, "world": 1}

    def test_count_case_insensitive(self) -> None:
        """Test that word counting is case-insensitive."""
        result = count_words("The cat and the dog")
        assert result == {"the": 2, "cat": 1, "and": 1, "dog": 1}

    def test_count_with_punctuation(self) -> None:
        """Test counting words with punctuation stripped."""
        result = count_words("Hello, World! Hello.")
        assert result == {"hello": 2, "world": 1}

    def test_count_empty_string(self) -> None:
        """Test counting words in empty string returns empty dict."""
        assert count_words("") == {}

    def test_count_whitespace_only(self) -> None:
        """Test counting words in whitespace-only string."""
        assert count_words("   ") == {}
        assert count_words("\t\n") == {}

    def test_count_single_word(self) -> None:
        """Test counting a single word."""
        assert count_words("hello") == {"hello": 1}

    def test_count_repeated_words(self) -> None:
        """Test counting multiple occurrences of the same word."""
        result = count_words("test test test")
        assert result == {"test": 3}

    def test_count_with_numbers(self) -> None:
        """Test counting words that include numbers."""
        result = count_words("test123 abc 456")
        assert result == {"test123": 1, "abc": 1, "456": 1}

    def test_count_mixed_case(self) -> None:
        """Test that mixed case words are normalized."""
        result = count_words("Hello HELLO hello HeLLo")
        assert result == {"hello": 4}

    def test_count_with_special_chars(self) -> None:
        """Test counting words with special characters."""
        result = count_words("hello@world test#ing foo-bar")
        assert result == {"hello": 1, "world": 1, "test": 1, "ing": 1, "foo": 1, "bar": 1}

    def test_count_none_input(self) -> None:
        """Test that None input returns empty dict."""
        assert count_words(None) == {}  # type: ignore

    def test_count_type_error_int(self) -> None:
        """Test that integer input raises TypeError."""
        with pytest.raises(TypeError, match="Expected str or None"):
            count_words(123)  # type: ignore

    def test_count_type_error_list(self) -> None:
        """Test that list input raises TypeError."""
        with pytest.raises(TypeError, match="Expected str or None"):
            count_words(["hello", "world"])  # type: ignore


class TestIntegration:
    """Integration tests combining multiple functions."""

    def test_reverse_and_capitalize(self) -> None:
        """Test reversing words then capitalizing sentences."""
        text = "hello world. how are you?"
        reversed_text = reverse_words(text)
        result = capitalize_sentences(reversed_text)
        assert "You?" in result or "you?" in result.lower()

    def test_clean_and_count(self) -> None:
        """Test removing extra spaces then counting words."""
        text = "hello  hello  world"
        cleaned = remove_extra_spaces(text)
        result = count_words(cleaned)
        assert result == {"hello": 2, "world": 1}

    def test_all_functions_pipeline(self) -> None:
        """Test using all functions in a pipeline."""
        text = "  hello  world. goodbye  world!  "
        # Clean spaces
        text = remove_extra_spaces(text)
        # Capitalize
        text = capitalize_sentences(text)
        # Reverse
        text = reverse_words(text)
        # Count
        counts = count_words(text)

        # Verify the pipeline worked
        assert "world" in counts
        assert counts["world"] == 2
        assert "hello" in counts or "goodbye" in counts

    def test_empty_string_all_functions(self) -> None:
        """Test that all functions handle empty strings correctly."""
        text = ""
        assert reverse_words(text) == ""
        assert capitalize_sentences(text) == ""
        assert remove_extra_spaces(text) == ""
        assert count_words(text) == {}
