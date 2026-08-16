from __future__ import annotations

import hashlib
from functools import lru_cache
from typing import NewType

TextId = NewType("TextId", str)
"""A hash-based identifier for a translatable string."""


@lru_cache(maxsize=8192)
def _text_id(text: str) -> TextId:
    """The 12-hex MD5 ID of a text, memoized by content.

    The ID is a pure function of the text's UTF-8 bytes, so caching by
    content is always correct. The runtime creates a fresh ``Text`` per
    call, so without this cache the same MD5 would be recomputed on
    every render; the LRU bound keeps dynamically generated texts from
    growing memory without limit.
    """
    return TextId(hashlib.md5(text.encode("utf-8")).hexdigest()[:12])


class Text(str):
    """A translatable source text with a hash-based ID."""

    @property
    def id(self) -> TextId:
        """The 12-hex MD5 ID of this text."""
        return _text_id(self)

    @classmethod
    def id_of(cls, text: str) -> TextId:
        """Return the ID for any text without keeping the object alive."""
        return _text_id(text)


TextMap = dict[TextId, str]
"""A mapping from ``TextId`` to the corresponding text."""
