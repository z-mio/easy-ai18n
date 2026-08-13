from typing import TYPE_CHECKING

from .i18n import I18n, LocaleContent, PostLocaleSelector, PreLocaleSelector
from .loader import Loader

if TYPE_CHECKING:
    from .builder import Builder

__all__ = [
    "Builder",
    "I18n",
    "LocaleContent",
    "PreLocaleSelector",
    "PostLocaleSelector",
    "Loader",
]


def __getattr__(name: str) -> object:
    if name == "Builder":
        from .builder import Builder

        return Builder
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
