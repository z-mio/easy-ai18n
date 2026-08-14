"""
Translation function and language selector.
"""

import inspect
import sys
from pathlib import Path
from types import FrameType
from typing import TYPE_CHECKING, Self, SupportsIndex, overload

from loguru import logger

from ._loader import Loader
from ._parser import ASTParser, StringData
from ._utils import generate_id
from .errors import EvaluationError, FormatError, UnsupportedSyntaxError

if TYPE_CHECKING:
    import ast

__all__ = [
    "PreLocaleSelector",
    "LocaleContent",
    "I18n",
    "PostLocaleSelector",
]


class PreLocaleSelector:
    """Pre-call language selector.

    Used via ``_[locale]("text")`` syntax.
    """

    def __init__(self, *, i18n: "I18n", sep: str, locale: str | None = None):
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

        Args:
            args: The text parts to translate.
            sep: The separator between text parts. Defaults to the
                configured separator.

        Returns:
            The translated string.
        """
        current_frame = inspect.currentframe()
        frame = current_frame.f_back if current_frame else None
        return self.i18n.t(*args, sep=sep or self.sep, frame=frame)[self.locale]


class LocaleContent(str):
    """Translated content with multi-locale access.

    Behaves like a string in the default locale and supports locale
    selection via ``content["locale"]`` or ``content(locale)``.
    """

    def __new__(
        cls,
        *,
        text: str,
        locales_dict: dict[str, dict[str, str]],
        variables: dict[str, object] | None = None,
        locale: str | None = None,
        post_locale_selector: type["PostLocaleSelector"] | None = None,
    ) -> Self:
        return str.__new__(cls, text)

    def __init__(
        self,
        *,
        text: str,
        locales_dict: dict[str, dict[str, str]],
        variables: dict[str, object] | None = None,
        locale: str | None = None,
        post_locale_selector: type["PostLocaleSelector"] | None = None,
    ):
        self._text = text
        self._locales_dict = locales_dict
        self._variables = variables or {}
        self._locale = locale
        self._post_locale_selector = post_locale_selector or PostLocaleSelector

    def __str__(self) -> str:
        return self.__call__(self._locale)

    def __repr__(self) -> str:
        return self.__call__(self._locale)

    @overload
    def __getitem__(self, locale: SupportsIndex | slice) -> str: ...

    @overload
    def __getitem__(self, locale: str | None) -> str: ...

    def __getitem__(self, locale: SupportsIndex | slice | str | None) -> str:
        """Select a locale via ``_[locale]`` syntax.

        Args:
            locale: The locale code to retrieve.

        Returns:
            The translated string for the given locale.
        """
        if isinstance(locale, (SupportsIndex, slice)):
            return super().__getitem__(locale)
        return self.__call__(locale)

    def __call__(self, locale: str | None) -> str:
        """Select a locale via ``_(locale)`` syntax.

        Args:
            locale: The locale code to retrieve.

        Returns:
            The translated string for the given locale.
        """
        return str(
            self._post_locale_selector(
                text=self._text,
                locales_dict=self._locales_dict,
                variables=self._variables,
                locale=locale,
            )
        )

    def __int__(self) -> int:
        return int(self.__str__())


class PostLocaleSelector:
    """Post-call language selector.

    Used via ``_("text")[locale]`` or ``_("text")(locale)`` syntax.
    """

    def __init__(
        self,
        *,
        text: str,
        locales_dict: dict[str, dict[str, str]],
        variables: dict[str, object] | None = None,
        locale: str | None = None,
    ):
        """Initialize PostLocaleSelector.

        Args:
            text: The text to translate.
            locales_dict: The translation data for all locales.
            variables: A dictionary of f-string variable placeholders
                and their values.
            locale: The default locale code.
        """
        self.text = text
        self.locales_dict = locales_dict
        self.variables = variables or {}
        self.locale = locale

    def __str__(self) -> str:
        return self.__getitem__(self.locale)

    def __repr__(self) -> str:
        return self.__getitem__(self.locale)

    def __getitem__(self, locale: str | None) -> str:
        """Select a locale via ``[locale]`` syntax.

        Args:
            locale: The locale code to retrieve.

        Returns:
            The translated string.
        """
        return self.format(locale)

    def format(self, locale: str | None = None) -> str:
        """Format the string and apply translation.

        Args:
            locale: The locale code to translate to. If ``None``,
                the original text is returned with variables
                substituted.

        Returns:
            The formatted and translated string.
        """
        if not locale:
            return self._format(self.text)
        translated = self.get_by_text(self.text, locale)
        return self._format(translated)

    def _format(self, raw_string: str) -> str:
        for v in self.variables:
            raw_string = raw_string.replace(v, str(self.variables[v]))
        return raw_string

    def get_by_text(self, text: str, locale: str | None = None) -> str:
        if locale is None:
            return text
        return self.locales_dict.get(locale, {}).get(generate_id(text), text)


class I18n:
    def __init__(
        self,
        sep: str,
        locales_dir: Path,
        func_names: list[str],
        enabled_locales: list[str] | None = None,
        default_locale: str | None = None,
        pre_locale_selector: type[PreLocaleSelector] | None = None,
        post_locale_selector: type[PostLocaleSelector] | None = None,
    ) -> None:
        """Initialize I18n.

        Args:
            enabled_locales: The list of enabled language codes.
            default_locale: The default locale code.
            sep: The separator between text parts.
            func_names: The names of translation functions to
                recognize during AST parsing.
            pre_locale_selector: The pre-call locale selector class.
            post_locale_selector: The post-call locale selector class.
        """
        self._cache: dict[str, ast.Call] = {}
        self._parse_failures: set[str] = set()

        self.default_locale = default_locale
        self.enabled_locales = list(enabled_locales) if enabled_locales else None
        if self.enabled_locales and self.default_locale and self.default_locale not in self.enabled_locales:
            self.enabled_locales.append(self.default_locale)

        self.sep = sep
        self.locales_dir = locales_dir
        self.func_names = func_names
        self.pre_locale_selector = pre_locale_selector or PreLocaleSelector
        self.post_locale_selector = post_locale_selector or PostLocaleSelector
        self.content = LocaleContent
        self.locales_dict = Loader(self.locales_dir).load_locales_file(self.enabled_locales)

    def t(self, *args: object, sep: str | None = None, frame: FrameType | None = None) -> LocaleContent:
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
        original = sep.join([str(item) for item in args])
        f = frame or sys._getframe(1)
        if not f:
            return self.content(
                text=original,
                locales_dict=self.locales_dict,
                post_locale_selector=self.post_locale_selector,
            )
        positions = (
            f.f_lineno,
            f.f_lasti,
            f.f_code.co_name,
            f.f_code.co_filename,
        )
        cache_key = generate_id(str(positions))

        # 解析错误的内容直接返回原文
        if cache_key in self._parse_failures:
            return self.content(
                text=original,
                locales_dict=self.locales_dict,
                post_locale_selector=self.post_locale_selector,
            )

        # 获取缓存的节点
        call_node = self._cache.get(cache_key, None)

        try:
            result = ASTParser(sep=sep, func_names=self.func_names).extract(frame=f, call_node=call_node)
            return self._handle_cache(original, cache_key, result)
        except (FormatError, EvaluationError, UnsupportedSyntaxError):
            logger.exception("I18N parse error")
            self._parse_failures.add(cache_key)
            return self.content(
                text=original,
                locales_dict=self.locales_dict,
                post_locale_selector=self.post_locale_selector,
            )
        except Exception:
            logger.exception("Unexpected I18N error")
            self._parse_failures.add(cache_key)
            return self.content(
                text=original,
                locales_dict=self.locales_dict,
                post_locale_selector=self.post_locale_selector,
            )

    def _handle_cache(self, original: str, cache_key: str, result: StringData | None) -> LocaleContent:
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
                locales_dict=self.locales_dict,
                post_locale_selector=self.post_locale_selector,
            )

        self._cache[cache_key] = result.call_node
        return self.content(
            text=result.string,
            locales_dict=self.locales_dict,
            variables=result.variables,
            locale=self.default_locale,
            post_locale_selector=self.post_locale_selector,
        )

    def clear_cache(self) -> None:
        """Clear the AST parse cache and failure record."""
        self._cache.clear()
        self._parse_failures.clear()

    def __getitem__(self, locale: str) -> PreLocaleSelector:
        """Select a locale via ``I18n[locale]`` syntax.

        Args:
            locale: The locale code to select.

        Returns:
            A ``PreLocaleSelector`` that translates all subsequent
            calls to the given locale.
        """
        return self.pre_locale_selector(i18n=self, locale=locale, sep=self.sep)

    def __call__(self, *args: object, sep: str | None = None) -> LocaleContent:
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
