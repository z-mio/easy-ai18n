from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING

from .i18n import I18n, LocaleContent, PostLocaleSelector, PreLocaleSelector

if TYPE_CHECKING:
    from .translators import BaseBulkTranslator, BaseItemTranslator

__all__ = [
    "EasyAI18n",
    "I18n",
    "PostLocaleSelector",
    "PreLocaleSelector",
    "LocaleContent",
]


class EasyAI18n:
    def __init__(
        self,
        func_names: str | list[str] | None = None,
        sep: str | None = None,
        locales_dir: str | Path | None = None,
    ):
        """Initialize EasyAI18n.

        Args:
            func_names: The names of translation functions to
                recognize (defaults to ``["_"]``).
            sep: The separator between text parts (defaults to
                a space).
            locales_dir: The directory for YAML translation files
                (defaults to ``./i18n``).
        """
        self.func_names = func_names if isinstance(func_names, list) else [func_names] if func_names else ["_"]
        self.sep = sep or " "
        self.locales_dir = Path(locales_dir) if locales_dir else Path.cwd() / "i18n"
        self.locales_dir.mkdir(parents=True, exist_ok=True)

    def build(
        self,
        to_locales: str | list[str],
        project_root: str | Path | None = None,
        include: list[str] | None = None,
        exclude: list[str] | None = None,
        translator: BaseItemTranslator | BaseBulkTranslator | None = None,
        max_concurrency: int | None = None,
        show_progress: bool = True,
    ) -> None:
        """Build translation files (synchronous wrapper).

        Args:
            to_locales: The target language codes to translate to.
            project_root: The project root directory.
            include: File or directory patterns to include.
            exclude: File or directory patterns to exclude.
            translator: The translator instance. Defaults to
                ``GoogleTranslator``.
            max_concurrency: The maximum number of concurrent
                translation tasks.
            show_progress: Whether to show the translation progress
                bar.
        """
        return asyncio.run(
            self.build_async(
                to_locales,
                project_root,
                include,
                exclude,
                translator,
                max_concurrency,
                show_progress,
            )
        )

    async def build_async(
        self,
        to_locales: str | list[str],
        project_root: str | Path | None = None,
        include: list[str] | None = None,
        exclude: list[str] | None = None,
        translator: BaseItemTranslator | BaseBulkTranslator | None = None,
        max_concurrency: int | None = None,
        show_progress: bool = True,
    ) -> None:
        """Build translation files asynchronously.

        Args:
            to_locales: The target language codes to translate to.
            project_root: The project root directory.
            include: File or directory patterns to include.
            exclude: File or directory patterns to exclude.
            translator: The translator instance. Defaults to
                ``GoogleTranslator``.
            max_concurrency: The maximum number of concurrent
                translation tasks.
            show_progress: Whether to show the translation progress
                bar.
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
            show_progress=show_progress,
            max_concurrency=max_concurrency,
        )
        await builder.run()

    def i18n(
        self,
        default_locale: str | None = None,
        enabled_locales: str | list[str] | None = None,
        pre_locale_selector: type[PreLocaleSelector] | None = None,
        post_locale_selector: type[PostLocaleSelector] | None = None,
    ) -> I18n:
        """Create an ``I18n`` instance for translation.

        Args:
            default_locale: The default locale code.
            enabled_locales: The list of enabled language codes.
                Defaults to all available locales.
            pre_locale_selector: The pre-call locale selector class.
            post_locale_selector: The post-call locale selector class.

        Returns:
            An ``I18n`` instance.
        """
        return I18n(
            default_locale=default_locale,
            enabled_locales=[enabled_locales] if isinstance(enabled_locales, str) else enabled_locales,
            sep=self.sep,
            locales_dir=self.locales_dir,
            func_names=self.func_names,
            pre_locale_selector=pre_locale_selector,
            post_locale_selector=post_locale_selector,
        )
