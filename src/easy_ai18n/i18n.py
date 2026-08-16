"""
Translation function and language selector.
"""

import inspect
import sys
from pathlib import Path
from types import FrameType
from typing import TYPE_CHECKING, Self, SupportsIndex

from loguru import logger

from ._loader import Loader
from ._parser import ASTParser, StringData
from ._types import Text, TextMap
from .errors import EvaluationError, FormatError, UnsupportedSyntaxError

if TYPE_CHECKING:
    import ast

__all__ = [
    "PreLocaleSelector",
    "LocaleContent",
    "I18n",
    "PostLocaleSelector",
]


class PreLocaleSelector[L]:
    """Pre-call language selector.

    Used via ``_[locale]("text")`` syntax.
    """

    def __init__(self, *, i18n: "I18n[L]", sep: str, locale: L):
        self.i18n = i18n
        self.sep = sep
        self.locale = locale

    def __str__(self) -> str:
        return ""

    def __repr__(self) -> str:
        return ""

    def __call__(self, *args: object, sep: str | None = None) -> str:
        """Translate text with the pre-selected locale.

        Called via ``_[locale]("text")``.

        When the selected locale is the source language, the joined
        arguments are already the final text: frame introspection,
        AST parsing and hashing are skipped entirely.

        Args:
            args: The text parts to translate.
            sep: The separator between text parts. Defaults to the
                configured separator.

        Returns:
            The translated string.
        """
        sep = sep or self.sep
        if self.locale == self.i18n.source_locale:
            return sep.join(str(item) for item in args)
        current_frame = inspect.currentframe()
        frame = current_frame.f_back if current_frame else None
        return self.i18n.t(*args, sep=sep, frame=frame)[self.locale]


class LocaleContent[L](str):
    """Translated content with multi-locale access.

    Behaves like a string in the default locale and supports locale
    selection via ``content["locale"]`` or ``content(locale)``.
    """

    def __new__(
        cls,
        *,
        text: str,
        locales: dict[str, TextMap],
        variables: dict[str, object] | None = None,
        locale: str,
        source_locale: str | None = None,
        post_locale_selector: "type[PostLocaleSelector[L]] | None" = None,
    ) -> Self:
        return str.__new__(cls, text)

    def __init__(
        self,
        *,
        text: str,
        locales: dict[str, TextMap],
        variables: dict[str, object] | None = None,
        locale: str,
        source_locale: str | None = None,
        post_locale_selector: "type[PostLocaleSelector[L]] | None" = None,
    ):
        self._text = text
        self._locales = locales
        self._variables = variables or {}
        self._locale = locale
        self._source_locale = source_locale
        self._post_locale_selector = post_locale_selector or PostLocaleSelector[L]

    def __str__(self) -> str:
        return self.__call__(self._locale)

    def __repr__(self) -> str:
        return self.__call__(self._locale)

    def __getitem__(self, locale: SupportsIndex | slice | L) -> str:
        """Select a locale via ``_("text")[locale]`` syntax.

        Args:
            locale: The locale identifier to retrieve.

        Returns:
            The translated string for the given locale.
        """
        if isinstance(locale, (SupportsIndex, slice)):
            return super().__getitem__(locale)
        return self.__call__(locale)

    def __call__(self, locale: L | str) -> str:
        """Select a locale via ``_("text")(locale)`` syntax.

        Args:
            locale: The locale identifier to retrieve.

        Returns:
            The translated string for the given locale.
        """
        return str(
            self._post_locale_selector(
                text=self._text,
                locales=self._locales,
                variables=self._variables,
                locale=locale,
                source_locale=self._source_locale,
            )
        )

    def __int__(self) -> int:
        return int(self.__str__())


class PostLocaleSelector[L]:
    """Post-call language selector.

    Used via ``_("text")[locale]`` or ``_("text")(locale)`` syntax.
    """

    def __init__(
        self,
        *,
        text: str,
        locales: dict[str, TextMap],
        variables: dict[str, object] | None = None,
        locale: L | str,
        source_locale: str | None = None,
    ):
        """Set up the post-call selector with translation data.

        Args:
            text: The text to translate.
            locales: The translation data for all locales.
            variables: A dictionary of f-string variable placeholders
                and their values.
            locale: The locale identifier.
            source_locale: The source language code. When the
                requested locale equals it, the original text is
                returned as-is (the source language never has a
                translation).
        """
        self.text = text
        self.locales = locales
        self.variables = variables or {}
        self.locale = locale
        self.source_locale = source_locale

    def __str__(self) -> str:
        return self.__getitem__(self.locale)

    def __repr__(self) -> str:
        return self.__getitem__(self.locale)

    def __getitem__(self, locale: L | str) -> str:
        """Select a locale via ``[locale]`` syntax.

        Args:
            locale: The locale identifier to retrieve.

        Returns:
            The translated string.
        """
        return self.format(locale)

    def format(self, locale: L | str) -> str:
        """Format the string and apply translation.

        Args:
            locale: The locale code to translate to. If not a string,
                the original text is returned with variables
                substituted.

        Returns:
            The formatted and translated string.
        """
        if not isinstance(locale, str):
            return self._format(self.text)
        # The source language never has a translation: the source text
        # is its own "translation". Short-circuit before hashing and
        # dictionary lookups.
        if self.source_locale is not None and locale == self.source_locale:
            return self._format(self.text)
        translated = self.locales.get(locale, {}).get(Text.id_of(self.text), self.text)
        return self._format(translated)

    def _format(self, raw_string: str) -> str:
        for v in self.variables:
            raw_string = raw_string.replace(v, str(self.variables[v]))
        return raw_string


class I18n[L]:
    def __init__(
        self,
        *,
        sep: str,
        locales_dir: Path,
        func_names: list[str],
        source_locale: str,
        default_locale: str | None = None,
        pre_locale_selector: type[PreLocaleSelector[L]] | None = None,
        post_locale_selector: type[PostLocaleSelector[L]] | None = None,
    ) -> None:
        """Set up the translation runtime.

        Args:
            sep: The separator between text parts.
            locales_dir: The directory for YAML translation files.
            func_names: The names of translation functions to
                recognize during AST parsing.
            source_locale: The source language of the translatable
                strings (e.g. ``"zh-hans"``).
            default_locale: The default locale code. Defaults to
                ``source_locale``.
            pre_locale_selector: The pre-call locale selector class.
            post_locale_selector: The post-call locale selector class.
        """
        self._cache: dict[str, ast.Call] = {}
        self._parse_failures: set[str] = set()

        self.source_locale = source_locale.lower()
        self.default_locale = default_locale or self.source_locale

        self.sep = sep
        self.locales_dir = locales_dir
        self.func_names = func_names
        self.pre_locale_selector: type[PreLocaleSelector[L]] = pre_locale_selector or PreLocaleSelector[L]
        self.post_locale_selector: type[PostLocaleSelector[L]] = post_locale_selector or PostLocaleSelector[L]
        self.content: type[LocaleContent[L]] = LocaleContent[L]
        self.locales = Loader(self.locales_dir).load_locales_file()

    def t(self, *args: object, sep: str | None = None, frame: FrameType | None = None) -> LocaleContent[L]:
        """Translate text by parsing the caller's AST node.

        This is the core translation entry point. It extracts the
        source code at the call site, parses the AST, and resolves
        f-string variables at runtime.

        Args:
            args: The text parts to join and translate.
            sep: The separator between text parts. Defaults to the
                configured separator.
            frame: The caller's stack frame. If ``None``, the current
                frame is used.

        Returns:
            A ``LocaleContent`` object that supports locale selection.
        """
        sep = sep or self.sep
        original = Text(sep.join([str(item) for item in args]))
        f = frame or sys._getframe(1)
        if not f:
            return self.content(
                text=original,
                locales=self.locales,
                locale=self.default_locale,
                source_locale=self.source_locale,
                post_locale_selector=self.post_locale_selector,
            )
        positions = (
            f.f_lineno,
            f.f_lasti,
            f.f_code.co_name,
            f.f_code.co_filename,
        )
        cache_key = Text.id_of(str(positions))

        if cache_key in self._parse_failures:
            return self.content(
                text=original,
                locales=self.locales,
                locale=self.default_locale,
                source_locale=self.source_locale,
                post_locale_selector=self.post_locale_selector,
            )

        call_node = self._cache.get(cache_key, None)

        try:
            result = ASTParser(sep=sep, func_names=self.func_names).extract(frame=f, call_node=call_node)
            return self._handle_cache(original, cache_key, result)
        except (FormatError, EvaluationError, UnsupportedSyntaxError):
            logger.exception("I18N parse error")
            self._parse_failures.add(cache_key)
            return self.content(
                text=original,
                locales=self.locales,
                locale=self.default_locale,
                source_locale=self.source_locale,
                post_locale_selector=self.post_locale_selector,
            )
        except Exception:
            logger.exception("Unexpected I18N error")
            self._parse_failures.add(cache_key)
            return self.content(
                text=original,
                locales=self.locales,
                locale=self.default_locale,
                source_locale=self.source_locale,
                post_locale_selector=self.post_locale_selector,
            )

    def _handle_cache(self, original: str, cache_key: str, result: StringData | None) -> LocaleContent[L]:
        """Handle the cache entry and return the result.

        If parsing succeeded, the AST node is cached; otherwise the
        failure is recorded so the original text is returned on
        subsequent calls.

        Args:
            original: The original joined text.
            cache_key: The cache key derived from the caller's frame
                position.
            result: The parsed result, or ``None`` if parsing failed.

        Returns:
            A ``LocaleContent`` object for the translated text.
        """
        if not result:
            self._parse_failures.add(cache_key)
            logger.error(f"I18N parse error: {original}")
            return self.content(
                text=original,
                locales=self.locales,
                locale=self.default_locale,
                source_locale=self.source_locale,
                post_locale_selector=self.post_locale_selector,
            )

        self._cache[cache_key] = result.call_node
        return self.content(
            text=result.string,
            locales=self.locales,
            variables=result.variables,
            locale=self.default_locale,
            source_locale=self.source_locale,
            post_locale_selector=self.post_locale_selector,
        )

    def clear_cache(self) -> None:
        """Clear the AST parse cache and failure record."""
        self._cache.clear()
        self._parse_failures.clear()

    def __getitem__(self, locale: L) -> PreLocaleSelector[L]:
        """Select a locale via ``I18n[locale]`` syntax.

        Args:
            locale: The locale identifier to select.

        Returns:
            A ``PreLocaleSelector`` that translates all subsequent
            calls to the given locale.
        """
        return self.pre_locale_selector(i18n=self, locale=locale, sep=self.sep)

    def __call__(self, *args: object, sep: str | None = None) -> LocaleContent[L]:
        """Translate text by calling ``I18n(...)``.

        Args:
            args: The text parts to translate.
            sep: The separator between text parts. Defaults to the
                configured separator.

        Returns:
            A ``LocaleContent`` object that supports locale selection.
        """
        current_frame = inspect.currentframe()
        frame = current_frame.f_back if current_frame else None
        return self.t(*args, sep=sep or self.sep, frame=frame)
