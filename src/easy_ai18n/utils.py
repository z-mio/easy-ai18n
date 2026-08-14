import hashlib
from pathlib import Path


def gen_id(text: object) -> str:
    """Generate a unique 12-character hex ID from the given text.

    Args:
        text: The input string to hash.

    Returns:
        A 12-character hexadecimal string.
    """
    text = str(text).encode("utf-8")
    return hashlib.md5(text).hexdigest()[:12]


def to_list[T](obj: T | list[T] | None) -> list[T]:
    if isinstance(obj, list):
        return obj
    elif obj is None:
        return []
    else:
        return [obj]


def to_path(path: str | Path | None) -> Path | None:
    if path is None:
        return None

    if isinstance(path, str):
        return Path(path)
    else:
        return path
