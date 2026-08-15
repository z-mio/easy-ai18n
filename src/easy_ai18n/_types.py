from __future__ import annotations

import hashlib
from functools import cached_property
from typing import NewType

TextId = NewType("TextId", str)
"""A hash-based identifier for a translatable string."""


class Text(str):
    """A translatable source text with a hash-based ID."""

    @cached_property
    def id(self) -> TextId:
        """The 12-hex MD5 ID of this text."""
        return TextId(hashlib.md5(self.encode("utf-8")).hexdigest()[:12])

    @classmethod
    def id_of(cls, text: str) -> TextId:
        """Return the ID for any text without keeping the object alive."""
        if isinstance(text, cls):
            return text.id
        return cls(text).id


TextMap = dict[TextId, str]
"""A mapping from ``TextId`` to the corresponding text."""
