"""
Translation dictionary builder.
"""

from __future__ import annotations

import ast
import asyncio
import copy
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml
from loguru import logger

from ._loader import Loader
from ._parser import ASTParser, StringData
from ._utils import generate_id
from .errors import BuildDependencyError, BuildError, TranslationError
from .translators import BaseBulkTranslator, BaseItemTranslator, GoogleTranslator

if TYPE_CHECKING:
    from tqdm import tqdm


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
        translator: BaseItemTranslator | BaseBulkTranslator | None = None,
        show_progress: bool = True,
        max_concurrency: int | None = None,
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
            show_progress: Whether to show the translation progress
                bar.
            max_concurrency: The maximum number of concurrent
                translation tasks.
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
        self.translator: BaseItemTranslator | BaseBulkTranslator = (
            translator if translator is not None else GoogleTranslator()
        )

        self.project_files = self.load_file()
        self.show_progress = show_progress
        self.max_concurrency = (
            max_concurrency
            if max_concurrency is not None
            else (30 if isinstance(self.translator, BaseItemTranslator) else 50)
        )
        self._locales_dict = Loader(self.locales_dir).load_locales_file(self.to_locales)

    async def run(self) -> None:
        if not self.is_changed():
            logger.info("Content unchanged, skipping build")
            return

        logger.info("Content changed, updating...")
        if await self.build():
            logger.success("Update complete")
        else:
            logger.error("Build failed")

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
        updated_locales_dict, to_be_translated = self.compute_changes()

        has_failures = False
        for locale, string_data_list in to_be_translated.items():
            try:
                id_to_string_data = {
                    generate_id(string_data.string): string_data for string_data in string_data_list
                }  # 原文id字典
                # 变量替换
                text_dict = {}
                for k, string_data in id_to_string_data.items():
                    if string_data.variables:
                        text = string_data.string
                        for i, var in enumerate(string_data.variables.keys()):
                            text = text.replace(var, f"{{{{{i}}}}}")
                        text_dict[k] = text
                    else:
                        text_dict[k] = string_data.string
                # 翻译
                translated_result = await self.translate(text_dict, locale)

                # 还原变量
                for k, string_data in id_to_string_data.items():
                    if string_data.variables:
                        text = translated_result[k]
                        for i, var in enumerate(string_data.variables.keys()):
                            text = text.replace(f"{{{{{i}}}}}", var)
                        translated_result[k] = text
            except TranslationError:
                logger.error(f"Translation to {locale} failed")
                has_failures = True
            except Exception:
                logger.exception(f"Unexpected error translating to {locale}:")
                has_failures = True
            else:
                updated_locales_dict.setdefault(locale, {})
                updated_locales_dict[locale] |= translated_result

        if save_to_file:
            for locale in updated_locales_dict:
                self.save_to_yaml(updated_locales_dict[locale], locale)
        return not has_failures

    def compute_changes(self, verbose: bool = True) -> tuple[dict[str, dict[str, str]], dict[str, list[StringData]]]:
        """Compute changes between source strings and existing translations.

        Identifies new strings that need translation and removes
        translations for strings that no longer exist in the source.

        Args:
            verbose: Whether to log change details at debug level.

        Returns:
            A tuple of ``(updated_locales_dict, to_be_translated)``,
            where ``updated_locales_dict`` is the cleaned-up
            translation dictionary and ``to_be_translated`` maps
            locales to lists of untranslated ``StringData``.
        """
        debug_log = logger.debug if verbose else lambda x: None
        id_to_string_data: dict[str, StringData] = {}
        for file in self.project_files:
            for string_data in self.extract_strings(file):
                if not string_data.string:  # 跳过空字符串 _("")
                    continue
                id_to_string_data[generate_id(string_data.string)] = string_data

        updated_locales_dict = copy.deepcopy(self._locales_dict)
        to_be_translated: dict[str, list[StringData]] = {}
        # 添加新语言
        for locale in self.to_locales:
            if locale not in updated_locales_dict:
                updated_locales_dict.setdefault(locale, {})
                debug_log(f"New locale: {locale}")
        # 移除过期语言
        for locale in list(self._locales_dict.keys()):
            if locale not in self.to_locales and locale in updated_locales_dict:
                del updated_locales_dict[locale]
                debug_log(f"Stale locale: {locale}")
        updated_locales_id_dict = self.extract_locale_ids(updated_locales_dict)
        # 添加新翻译
        for trans_id, string_data in id_to_string_data.items():
            for locale in updated_locales_dict:
                if trans_id in updated_locales_dict[locale]:
                    continue

                to_be_translated.setdefault(locale, [])
                if trans_id not in {generate_id(string_data.string) for string_data in to_be_translated[locale]}:
                    to_be_translated[locale].append(string_data)

                debug_log(
                    f"New text: {locale} - {
                        f'{string_data.string[:30]}...' if string_data.string[30:] else string_data.string
                    }"
                )
        # 移除过期翻译
        for locale in updated_locales_id_dict:
            for trans_id in list(updated_locales_id_dict[locale]):
                if trans_id in id_to_string_data:
                    continue
                if trans_id not in updated_locales_dict[locale]:
                    continue
                del updated_locales_dict[locale][trans_id]
                debug_log(f"Stale text: {locale} - {trans_id}")
        return updated_locales_dict, to_be_translated

    def load_file(self) -> list[Path]:
        project_files: list[Path] = []
        include_paths = [Path(p) for p in self.include] if self.include else []
        exclude_paths = [Path(p) for p in self.exclude]

        for root, dirs, files in self.project_root.walk():
            # 先做目录排除
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

        updated_locale_dict, to_be_translated = self.compute_changes(verbose=False)
        return bool(updated_locale_dict != self._locales_dict or to_be_translated)

    async def translate_items(self, text_id_dict: dict[str, str], to_locale: str) -> dict[str, str]:
        """Translate texts one by one.

        Args:
            text_id_dict: A dictionary of text IDs to texts.
            to_locale: The target language code.

        Returns:
            A dictionary of translated texts keyed by ID.
        """
        result: dict[str, str] = {}
        progress_bar = self.progress_bar(to_locale, len(text_id_dict))

        semaphore = asyncio.Semaphore(self.max_concurrency)
        translator = self.translator
        if not isinstance(translator, BaseItemTranslator):
            raise BuildError("translate_items requires a BaseItemTranslator")

        async def _translate_one(text: str, locale: str, sem: asyncio.Semaphore) -> str:
            async with sem:
                translated = await translator.translate(text, locale)
                progress_bar.update()
                return translated

        tasks: dict[str, asyncio.Task] = {
            key: asyncio.create_task(_translate_one(text, to_locale, semaphore)) for key, text in text_id_dict.items()
        }

        done, pending = await asyncio.wait(tasks.values(), timeout=300)
        for task in pending:
            task.cancel()
        progress_bar.close()

        for key, task in tasks.items():
            try:
                translated_text = task.result()
            except TranslationError:
                logger.error(f"→ [{to_locale}] Translation failed (id={key}, text={text_id_dict[key]})")
            except Exception:
                logger.exception(f"→ [{to_locale}] Unexpected error (id={key}):")
            else:
                result[key] = translated_text

        return result

    async def translate_bulk(self, text_id_dict: dict[str, str], to_locale: str) -> dict[str, str]:
        """Translate texts in bulk.

        Args:
            text_id_dict: A dictionary of text IDs to texts.
            to_locale: The target language code.

        Returns:
            A dictionary of translated texts keyed by ID.
        """
        translator = self.translator
        if not isinstance(translator, BaseBulkTranslator):
            raise BuildError("translate_bulk requires a BaseBulkTranslator")
        with self.progress_bar(to_locale, 1) as progress_bar:
            all_results: dict[str, str] = {}
            items = list(text_id_dict.items())
            for i in range(0, len(items), self.max_concurrency):
                batch = dict(items[i : i + self.max_concurrency])
                batch_results = await translator.translate(batch, to_locale)
                all_results |= batch_results
            progress_bar.update()
        return all_results

    async def translate(self, text_id_dict: dict[str, str], to_locale: str) -> dict[str, str]:
        if isinstance(self.translator, BaseItemTranslator):
            return await self.translate_items(text_id_dict, to_locale)
        elif isinstance(self.translator, BaseBulkTranslator):
            return await self.translate_bulk(text_id_dict, to_locale)
        else:
            raise BuildError(f"Unsupported translator type: {type(self.translator).__name__}")

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

    def save_to_yaml(self, locale_dict: dict[str, str], locale: str) -> None:
        """Save a translation dictionary to a YAML file.

        Args:
            locale_dict: The translation dictionary to save.
            locale: The locale code, used as the filename.
        """
        with open(self.locales_dir / f"{locale}.yaml", "w", encoding="utf-8") as f:
            yaml.dump(locale_dict, f, allow_unicode=True)

    @staticmethod
    def extract_locale_ids(locales_dict: dict[str, dict[str, Any]]) -> dict[str, list[str]]:
        """Extract all translation IDs from a locales dictionary.

        Args:
            locales_dict: The locales dictionary.

        Returns:
            A dictionary mapping locale codes to lists of translation
            IDs.
        """

        if not locales_dict:
            return {}

        return {locale: list(locale_dict) for locale, locale_dict in locales_dict.items()}

    def progress_bar(self, locale: str, total: int) -> tqdm:
        try:
            from tqdm import tqdm
        except ImportError as e:
            raise BuildDependencyError() from e

        return tqdm(
            total=total,
            desc=f"⏳ Translating → {locale}",
            unit="items",
            ncols=80,
            bar_format="{desc}: {percentage:3.0f}%|{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}]",
            colour="blue",
            disable=not self.show_progress,
        )
