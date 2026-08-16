"""
Translation dictionary builder.
"""

from __future__ import annotations

import ast
import asyncio
import copy
import os
from collections.abc import Callable
from pathlib import Path

import yaml
from loguru import logger

from ._loader import Loader
from ._parser import ASTParser, StringData
from ._progress import ProgressHandle, translation_progress
from ._types import TextId, TextMap
from .errors import TranslationError
from .translators import BaseTranslator, GoogleTranslator


class Builder:
    def __init__(
        self,
        *,
        sep: str,
        func_names: list[str],
        locales_dir: Path,
        to_locales: list[str],
        source_locale: str,
        project_root: Path | None = None,
        include: list[str] | None = None,
        exclude: list[str] | None = None,
        translator: BaseTranslator | None = None,
        show_progress: bool = True,
        concurrent_locales: bool = True,
        max_retries: int = 1,
    ):
        """Set up the translation build pipeline.

        Args:
            sep: The separator between text parts.
            func_names: The names of translation functions to
                recognize during AST parsing.
            locales_dir: The directory for YAML translation files.
            to_locales: The target language codes to translate to.
            source_locale: The source language of the translatable
                strings.
            project_root: The project root directory.
            include: File or directory patterns to include.
            exclude: File or directory patterns to exclude.
            translator: The translator instance. Defaults to
                ``GoogleTranslator``.
            show_progress: Whether to display progress.  ``False`` stays silent.
                Defaults to ``True``.
            concurrent_locales: Whether to translate all locales in
                parallel. ``True`` (default) is faster but issues more
                API calls at once; set to ``False`` for rate-limited
                free APIs.
            max_retries: How many extra attempts a locale gets after
                a translation failure. Defaults to ``1``.
        """
        self.project_root = project_root or Path(os.getcwd())
        self.include = include or []
        self.exclude = exclude or []
        self.default_exclude = [".venv", "venv", ".git", ".idea"]
        self.func_names = func_names
        self.sep = sep
        self.to_locales = [i.lower() for i in to_locales]
        self.locales_dir = locales_dir
        self.source_locale = source_locale
        self.translator: BaseTranslator = GoogleTranslator() if translator is None else translator
        self.show_progress = show_progress
        self.concurrent_locales = concurrent_locales
        self.max_retries = max_retries

        self.project_files = self.load_file()
        self._locales = Loader(self.locales_dir).load_locales_file(self.to_locales)

    async def run(self) -> None:
        if not self.is_changed():
            logger.info("Content unchanged, skipping build")
            return

        await self.build()

    async def build(self, save_to_file: bool = True) -> bool:
        """Build the translation dictionary.

        Compares the current source strings with the existing
        translation files, translates new content, and optionally
        persists the results.

        Args:
            save_to_file: Whether to save the results to YAML files.

        Returns:
            ``True`` if the build completed successfully.
        """
        locales, to_be_translated = self.compute_changes()
        locale_totals = {locale: len(entries) for locale, entries in to_be_translated.items()}

        has_failures = False
        errors: dict[str, str] = {}

        async def run_locale(locale: str) -> TextMap | None:
            nonlocal has_failures
            entries = to_be_translated[locale]
            error: Exception | None = None
            try:
                return await self._translate_locale(locale, entries, handle)
            except TranslationError as e:
                logger.error(f"Translation to {locale} failed: {e}")
                error = e
            except Exception as e:
                logger.exception(f"Unexpected error translating to {locale}: {e}")
                error = e

            # Auto-retry: rerun silently so progress is not
            # double-counted, then top up progress on success.
            if self.max_retries > 0:
                handle.retrying(locale)
                try:
                    result = await self._translate_locale(locale, entries, ProgressHandle())
                except TranslationError as e:
                    logger.error(f"Retry for {locale} failed: {e}")
                    error = e
                except Exception as e:
                    logger.exception(f"Unexpected error retrying {locale}: {e}")
                    error = e
                else:
                    handle.succeed(locale, completed=len(entries))
                    return result

            handle.fail(locale)
            errors[locale] = str(error) if error is not None else "unknown error"
            has_failures = True
            return None

        async with translation_progress(locale_totals, show_progress=self.show_progress) as handle:
            if self.concurrent_locales:
                results = await asyncio.gather(*(run_locale(locale) for locale in to_be_translated))
            else:
                results = [await run_locale(locale) for locale in to_be_translated]

            for locale, result in zip(to_be_translated, results, strict=True):
                if result is None:
                    continue
                handle.succeed(locale)
                locales.setdefault(locale, {})
                locales[locale] |= result
            handle.finish(ok=not has_failures)

        handle.report_errors(errors)

        if save_to_file:
            for locale in locales:
                self.save_to_yaml(locales[locale], locale)
        return not has_failures

    async def _translate_locale(
        self,
        locale: str,
        entries: list[StringData],
        handle: ProgressHandle,
    ) -> TextMap:
        """Translate every new string of one locale.

        Replaces f-string variable placeholders before translation and
        restores them afterwards. Raises on failure so the caller can
        apply retry logic.

        Args:
            locale: The target language code.
            entries: Untranslated string data for this locale.
            handle: Progress handle for chunk-level advancement.

        Returns:
            The translated texts keyed by ID, with variables restored.
        """
        entry_map = {s.string.id: s for s in entries}
        texts: TextMap = {}
        for k, s in entry_map.items():
            if s.variables:
                text: str = s.string
                for i, var in enumerate(s.variables.keys()):
                    text = text.replace(var, f"{{{{{i}}}}}")
                texts[TextId(k)] = text
            else:
                texts[TextId(k)] = s.string

        translated_result = await self.translate(
            texts,
            locale,
            on_progress=lambda n: handle.advance(locale, n),
        )

        for k, s in entry_map.items():
            if s.variables:
                text = translated_result[TextId(k)]
                for i, var in enumerate(s.variables.keys()):
                    text = text.replace(f"{{{{{i}}}}}", var)
                translated_result[TextId(k)] = text
        return translated_result

    def compute_changes(self) -> tuple[dict[str, TextMap], dict[str, list[StringData]]]:
        """Compute changes between source strings and existing translations.

        Identifies new strings that need translation and removes
        translations for strings that no longer exist in the source.

        Returns:
            A tuple of ``(locales, to_be_translated)``,
            where ``locales`` is the cleaned-up
            translation dictionary and ``to_be_translated`` maps
            locales to lists of untranslated ``StringData``.
        """
        entries: dict[TextId, StringData] = {}
        for file in self.project_files:
            for string_data in self.extract_strings(file):
                if not string_data.string:
                    continue
                entries[string_data.string.id] = string_data

        locales = copy.deepcopy(self._locales)
        to_be_translated: dict[str, list[StringData]] = {}
        for locale in self.to_locales:
            if locale not in locales:
                locales.setdefault(locale, {})
        for locale in list(self._locales.keys()):
            if locale not in self.to_locales and locale in locales:
                del locales[locale]
        updated_locales_id_dict = self.extract_locale_ids(locales)
        for trans_id, string_data in entries.items():
            for locale in locales:
                if trans_id in locales[locale]:
                    continue

                to_be_translated.setdefault(locale, [])
                if trans_id not in {string_data.string.id for string_data in to_be_translated[locale]}:
                    to_be_translated[locale].append(string_data)

        for locale in updated_locales_id_dict:
            for old_id in list(updated_locales_id_dict[locale]):
                if old_id in entries:
                    continue
                if old_id not in locales[locale]:
                    continue
                del locales[locale][TextId(old_id)]
        return locales, to_be_translated

    def load_file(self) -> list[Path]:
        project_files: list[Path] = []
        include_paths = [Path(p) for p in self.include] if self.include else []
        exclude_paths = [Path(p) for p in self.exclude]

        for root, dirs, files in self.project_root.walk():
            dirs[:] = [
                d
                for d in dirs
                if not any(
                    (Path(root) / d).relative_to(self.project_root).match(str(exc))
                    for exc in self.default_exclude + exclude_paths
                )
            ]
            for fname in files:
                if not fname.endswith(".py"):
                    continue

                full = Path(root) / fname
                rel = full.relative_to(self.project_root)

                if include_paths and not any(str(rel).startswith(str(ip)) for ip in include_paths):
                    continue

                if any(str(rel).startswith(str(ep)) for ep in exclude_paths):
                    continue

                project_files.append(full)

        return project_files

    def is_changed(self) -> bool:
        """Check whether the translation data has changed.

        Returns:
            ``True`` if there are new or removed strings compared to
            the existing translation files.
        """

        locales, to_be_translated = self.compute_changes()
        return bool(locales != self._locales or to_be_translated)

    async def translate(
        self,
        texts: TextMap,
        to_locale: str,
        on_progress: Callable[[int], None] | None = None,
    ) -> TextMap:
        """Translate texts via the configured translator.

        Args:
            texts: A dictionary of text IDs to texts.
            to_locale: The target language code.
            on_progress: Called with the chunk size after each
                completed chunk, for progress reporting.

        Returns:
            A dictionary of translated texts keyed by ID.
        """
        return await self.translator.translate(texts, to_locale, on_progress=on_progress)

    def extract_strings(self, file: Path) -> list[StringData]:
        """Extract all translatable strings from a Python file.

        Args:
            file: The path to the Python file.

        Returns:
            A list of ``StringData`` objects for each translation
            call found in the file.
        """
        source = file.read_text(encoding="utf-8")
        module = ast.parse(source)
        return ASTParser(sep=self.sep, func_names=self.func_names).extract_all(
            node=module,
            source_path=file,
            source=source,
        )

    def save_to_yaml(self, texts: TextMap, locale: str) -> None:
        """Save a translation dictionary to a YAML file.

        Args:
            texts: The translation dictionary to save.
            locale: The locale code, used as the filename.
        """
        with open(self.locales_dir / f"{locale}.yaml", "w", encoding="utf-8") as f:
            yaml.dump(texts, f, allow_unicode=True)

    @staticmethod
    def extract_locale_ids(locales_dict: dict[str, TextMap]) -> dict[str, list[str]]:
        """Extract all translation IDs from a locales dictionary.

        Args:
            locales_dict: The locales dictionary.

        Returns:
            A dictionary mapping locale codes to lists of translation
            IDs.
        """

        if not locales_dict:
            return {}

        return {locale: list(texts) for locale, texts in locales_dict.items()}
