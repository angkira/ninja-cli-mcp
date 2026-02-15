"""
Parallel Test 2: String utilities module.
This is an independent task that doesn't depend on other parallel tasks.
"""


def reverse_string(text: str) -> str:
    """Reverse a string."""
    return text[::-1]


def capitalize_first_letter(text: str) -> str:
    """Capitalize the first letter of a string."""
    if not text:
        return text
    return text[0].upper() + text[1:]


def count_vowels(text: str) -> int:
    """Count the number of vowels in text."""
    vowels = "aeiouAEIOU"
    return sum(1 for char in text if char in vowels)


def is_palindrome(text: str) -> bool:
    """Check if a string is a palindrome (ignoring spaces and case)."""
    clean_text = "".join(text.split()).lower()
    return clean_text == clean_text[::-1]


def word_frequency(text: str) -> dict[str, int]:
    """Get frequency of words in text."""
    words = text.lower().split()
    freq = {}
    for word in words:
        freq[word] = freq.get(word, 0) + 1
    return freq


if __name__ == "__main__":
    print(f"reverse('hello') = {reverse_string('hello')}")
    print(f"capitalize('hello') = {capitalize_first_letter('hello')}")
    print(f"vowels('hello world') = {count_vowels('hello world')}")
    print(f"palindrome('racecar') = {is_palindrome('racecar')}")
    print(f"word_freq('hello hello world') = {word_frequency('hello hello world')}")
