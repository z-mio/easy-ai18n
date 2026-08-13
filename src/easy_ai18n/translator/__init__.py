from typing import TYPE_CHECKING

from .base import BaseBulkTranslator, BaseItemTranslator

if TYPE_CHECKING:
    from .translator import GoogleTranslator, OpenAIBulkTranslator, OpenAIItemTranslator

__all__ = [
    "GoogleTranslator",
    "OpenAIItemTranslator",
    "OpenAIBulkTranslator",
    "BaseItemTranslator",
    "BaseBulkTranslator",
]


def __getattr__(name: str) -> object:
    if name in {"GoogleTranslator", "OpenAIItemTranslator", "OpenAIBulkTranslator"}:
        from . import translator

        return getattr(translator, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
