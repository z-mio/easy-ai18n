"""
Translation dictionary builder.
"""

from __future__ import annotations

import ast
import copy
import os
from pathlib import Path

import yaml
from loguru import logger

from ._loader import Loader
from ._parser import ASTParser, StringData
from ._types import TextId, TextMap
from ._utils import generate_id
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

        self.project_files = self.load_file()
        self._locales = Loader(self.locales_dir).load_locales_file(self.to_locales)

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
        locales, to_be_translated = self.compute_changes()

        has_failures = False
        for locale, entries in to_be_translated.items():
            try:
                entry_map = {generate_id(s.string): s for s in entries}
                texts: TextMap = {}
                for k, s in entry_map.items():
                    if s.variables:
                        text = s.string
                        for i, var in enumerate(s.variables.keys()):
                            text = text.replace(var, f"{{{{{i}}}}}")
                        texts[TextId(k)] = text
                    else:
                        texts[TextId(k)] = s.string

                translated_result = await self.translate(texts, locale)

                for k, s in entry_map.items():
                    if s.variables:
                        text = translated_result[TextId(k)]
                        for i, var in enumerate(s.variables.keys()):
                            text = text.replace(f"{{{{{i}}}}}", var)
                        translated_result[TextId(k)] = text
            except TranslationError:
                logger.error(f"Translation to {locale} failed")
                has_failures = True
            except Exception:
                logger.exception(f"Unexpected error translating to {locale}:")
                has_failures = True
            else:
                locales.setdefault(locale, {})
                locales[locale] |= translated_result

        if save_to_file:
            for locale in locales:
                self.save_to_yaml(locales[locale], locale)
        return not has_failures

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
        entries: dict[str, StringData] = {}
        for file in self.project_files:
            for string_data in self.extract_strings(file):
                if not string_data.string:
                    continue
                entries[generate_id(string_data.string)] = string_data

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
                if trans_id not in {generate_id(string_data.string) for string_data in to_be_translated[locale]}:
                    to_be_translated[locale].append(string_data)

        for locale in updated_locales_id_dict:
            for trans_id in list(updated_locales_id_dict[locale]):
                if trans_id in entries:
                    continue
                if trans_id not in locales[locale]:
                    continue
                del locales[locale][TextId(trans_id)]
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

    async def translate(self, texts: TextMap, to_locale: str) -> TextMap:
        """Translate texts via the configured translator.

        Args:
            texts: A dictionary of text IDs to texts.
            to_locale: The target language code.

        Returns:
            A dictionary of translated texts keyed by ID.
        """
        return await self.translator.translate_batch(texts, to_locale)

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
