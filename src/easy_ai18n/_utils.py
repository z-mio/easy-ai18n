import hashlib


def generate_id(v: str) -> str:
    """Generate a unique 12-character hex ID from the given text.

    Args:
        v: The input string to hash.

    Returns:
        A 12-character hexadecimal string.
    """
    return hashlib.md5(v.encode("utf-8")).hexdigest()[:12]
