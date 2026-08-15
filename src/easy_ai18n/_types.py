from typing import NewType

TextId = NewType("TextId", str)
"""A hash-based identifier for a translatable string."""

TextMap = dict[TextId, str]
"""A mapping from ``TextId`` to the corresponding text."""
