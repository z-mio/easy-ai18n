import hashlib


def generate_id(text: str) -> str:
    """Generate a unique 12-character hex ID from the given text.

    Args:
        text: The input string to hash.

    Returns:
        A 12-character hexadecimal string.
    """
    return hashlib.md5(text.encode("utf-8")).hexdigest()[:12]
