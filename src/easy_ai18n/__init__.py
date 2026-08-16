from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING, overload

from ._types import Text, TextId, TextMap
from .i18n import I18n, LocaleContent, PostLocaleSelector, PreLocaleSelector

if TYPE_CHECKING:
    from .translators import BaseTranslator

__all__ = [
    "EasyAI18n",
    "I18n",
    "PostLocaleSelector",
    "PreLocaleSelector",
    "LocaleContent",
    "Text",
    "TextId",
    "TextMap",
]


class EasyAI18n:
    def __init__(
        self,
        source_locale: str,
        *,
        func_names: str | list[str] | None = None,
        sep: str | None = None,
        locales_dir: str | Path | None = None,
    ):
        """Set up the i18n environment.

        Args:
            source_locale: The source language of the translatable
                strings (e.g. ``"zh-hans"``).
            func_names: The names of translation functions to
                recognize (defaults to ``["_"]``).
            sep: The separator between text parts (defaults to
                a space).
            locales_dir: The directory for YAML translation files
                (defaults to ``./i18n``).
        """
        self.source_locale = source_locale.lower()
        self.func_names = func_names if isinstance(func_names, list) else [func_names] if func_names else ["_"]
        self.sep = sep or " "
        self.locales_dir = Path(locales_dir) if locales_dir else Path.cwd() / "i18n"
        self.locales_dir.mkdir(parents=True, exist_ok=True)

    def build(
        self,
        to_locales: str | list[str],
        *,
        project_root: str | Path | None = None,
        include: list[str] | None = None,
        exclude: list[str] | None = None,
        translator: BaseTranslator | None = None,
        show_progress: bool = True,
        concurrent_locales: bool = True,
        max_retries: int = 1,
    ) -> None:
        """Build translation files (synchronous wrapper).

        Args:
            to_locales: The target language codes to translate to.
            project_root: The project root directory.
            include: File or directory patterns to include.
            exclude: File or directory patterns to exclude.
            translator: The translator instance. Defaults to
                ``GoogleTranslator``.
            show_progress: Whether to display progress.  ``False`` stays silent.
                Defaults to ``True``.
            concurrent_locales: Whether to translate all locales in
                parallel. Defaults to ``True``; set to ``False`` for
                rate-limited free APIs.
            max_retries: Extra attempts per locale after a failure.
                Defaults to ``1``.
        """
        return asyncio.run(
            self.build_async(
                to_locales,
                project_root=project_root,
                include=include,
                exclude=exclude,
                translator=translator,
                show_progress=show_progress,
                concurrent_locales=concurrent_locales,
                max_retries=max_retries,
            )
        )

    async def build_async(
        self,
        to_locales: str | list[str],
        *,
        project_root: str | Path | None = None,
        include: list[str] | None = None,
        exclude: list[str] | None = None,
        translator: BaseTranslator | None = None,
        show_progress: bool = True,
        concurrent_locales: bool = True,
        max_retries: int = 1,
    ) -> None:
        """Build translation files asynchronously.

        Args:
            to_locales: The target language codes to translate to.
            project_root: The project root directory.
            include: File or directory patterns to include.
            exclude: File or directory patterns to exclude.
            translator: The translator instance. Defaults to
                ``GoogleTranslator``.
            show_progress: Whether to display progress.  ``False`` stays silent.
                Defaults to ``True``.
            concurrent_locales: Whether to translate all locales in
                parallel. Defaults to ``True``; set to ``False`` for
                rate-limited free APIs.
            max_retries: Extra attempts per locale after a failure.
                Defaults to ``1``.
        """
        from ._builder import Builder

        builder = Builder(
            to_locales=[to_locales] if isinstance(to_locales, str) else to_locales,
            sep=self.sep,
            func_names=self.func_names,
            project_root=Path(project_root) if project_root else None,
            locales_dir=self.locales_dir,
            include=include,
            exclude=exclude,
            translator=translator,
            source_locale=self.source_locale,
            show_progress=show_progress,
            concurrent_locales=concurrent_locales,
            max_retries=max_retries,
        )
        await builder.run()

    @overload
    def i18n(
        self,
        default_locale: str | None = None,
        *,
        pre_locale_selector: None = None,
        post_locale_selector: None = None,
    ) -> I18n[str | None]: ...

    @overload
    def i18n[L](
        self,
        default_locale: str | None = None,
        *,
        pre_locale_selector: type[PreLocaleSelector[L]] | None = None,
        post_locale_selector: type[PostLocaleSelector[L]],
    ) -> I18n[L]: ...

    def i18n[L](
        self,
        default_locale: str | None = None,
        *,
        pre_locale_selector: type[PreLocaleSelector[L]] | None = None,
        post_locale_selector: type[PostLocaleSelector[L]] | None = None,
    ) -> I18n[L]:
        """Create an ``I18n`` instance for translation.

        Args:
            default_locale: The default locale code. Defaults to
                the ``source_locale`` set on ``EasyAI18n``.
            pre_locale_selector: The pre-call locale selector class.
            post_locale_selector: The post-call locale selector class.

        Returns:
            An ``I18n`` instance.
        """
        return I18n(
            default_locale=default_locale,
            source_locale=self.source_locale,
            sep=self.sep,
            locales_dir=self.locales_dir,
            func_names=self.func_names,
            pre_locale_selector=pre_locale_selector,
            post_locale_selector=post_locale_selector,
        )
