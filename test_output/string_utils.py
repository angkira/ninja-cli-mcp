"""String utility functions."""

def capitalize_sentence(text: str) -> str:
    """Capitalize first letter of sentence.
    
    Args:
        text: Input string
        
    Returns:
        Capitalized string
    """
    if not text:
        return text
    return text[0].upper() + text[1:] if len(text) > 1 else text.upper()


def reverse_string(text: str) -> str:
    """Reverse a string.
    
    Args:
        text: Input string
        
    Returns:
        Reversed string
    """
    return text[::-1]
