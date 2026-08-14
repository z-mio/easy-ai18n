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

from ..config import ic
from ..errors import BuildDependencyError
from ..translator import GoogleTranslator
from ..translator.base import BaseBulkTranslator, BaseItemTranslator
from ..utils import gen_id, to_path
from .loader import Loader
from .parser import ASTParser, StringData

if TYPE_CHECKING:
    from tqdm import tqdm


class Builder:
    def __init__(
        self,
        to_locales: list[str] | None = None,
        sep: str | None = None,
        func_names: list[str] | None = None,
        project_root: str | Path | None = None,
        locales_dir: str | Path | None = None,
        include: list[str] | None = None,
        exclude: list[str] | None = None,
        translator: BaseItemTranslator | BaseBulkTranslator | None = None,
        show_progress: bool = True,
        max_concurrency: int | None = None,
    ):
        """Initialize Builder.

        Args:
            to_locales: The target language codes to translate to.
            sep: The separator between text parts.
            func_names: The names of translation functions to
                recognize during AST parsing.
            project_root: The project root directory.
            locales_dir: The directory for YAML translation files.
            include: File or directory patterns to include.
            exclude: File or directory patterns to exclude.
            translator: The translator instance. Defaults to
                ``GoogleTranslator``.
            show_progress: Whether to show the translation progress
                bar.
            max_concurrency: The maximum number of concurrent
                translation tasks.
        """
        self.project_root = to_path(project_root) or Path(os.getcwd())
        self.include = include or []
        self.exclude = exclude or []
        self.default_exclude = [".venv", "venv", ".git", ".idea"]
        self.func_names = func_names or ic.func_names
        self.sep = sep or ic.sep
        if to_locales is None:
            raise ValueError("构建失败: to_locales 未配置")
        self.to_locales = to_locales
        self.locales_dir = to_path(locales_dir) or ic.locales_dir
        self.translator: BaseItemTranslator | BaseBulkTranslator = translator or GoogleTranslator()

        self.project_files = self.load_file()
        self.show_progress = show_progress
        self.max_concurrency = max_concurrency or (30 if isinstance(self.translator, BaseItemTranslator) else 50)
        self._locales_dict = Loader(self.locales_dir).load_locales_file(self.to_locales)

    async def run(self) -> None:
        if not self.is_changed():
            logger.info("内容无更新")
            return

        logger.info("内容有更新, 开始更新...")
        if await self.build():
            logger.success("更新完成")
            return
        else:
            logger.error("构建失败")
            return

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
        updated_locales_dict, to_be_translated = self.check_changes()

        for locale, sd_list in to_be_translated.items():
            try:
                text_id_dict = {gen_id(sd.string): sd for sd in sd_list}  # 原文id字典
                # 变量替换
                str_list = {}
                for k, sd in text_id_dict.items():
                    if sd.variables:
                        text = sd.string
                        for i, var in enumerate(sd.variables.keys()):
                            text = text.replace(var, f"{{{{{i}}}}}")
                        str_list[k] = text
                    else:
                        str_list[k] = sd.string
                # 翻译
                trans_result = await self.translate(str_list, locale)

                # 还原变量
                for k, sd in text_id_dict.items():
                    if sd.variables:
                        text = trans_result[k]
                        for i, var in enumerate(sd.variables.keys()):
                            text = text.replace(f"{{{{{i}}}}}", var)
                        trans_result[k] = text
            except Exception:
                logger.exception(f"翻译到 {locale} 失败:")
            else:
                updated_locales_dict.setdefault(locale, {})
                updated_locales_dict[locale] |= trans_result

        if save_to_file:
            for locale in updated_locales_dict:
                self.save_to_yaml(updated_locales_dict[locale], locale)
        return True

    def check_changes(self, log: bool = True) -> tuple[dict[str, dict[str, str]], dict[str, list[StringData]]]:
        """Check for changes between source strings and existing translations.

        Identifies new strings that need translation and removes
        translations for strings that no longer exist in the source.

        Args:
            log: Whether to log change details at debug level.

        Returns:
            A tuple of ``(updated_locales_dict, to_be_translated)``,
            where ``updated_locales_dict`` is the cleaned-up
            translation dictionary and ``to_be_translated`` maps
            locales to lists of untranslated ``StringData``.
        """
        lg = logger.debug if log else lambda x: None
        str_id_dict: dict[str, StringData] = {}
        for file in self.project_files:
            for sd in self.extract_strings(file):
                if not sd.string:  # 跳过空字符串 _("")
                    continue
                str_id_dict[gen_id(sd.string)] = sd

        updated_locales_dict = copy.deepcopy(self._locales_dict)
        to_be_translated: dict[str, list[StringData]] = {}
        # 添加新语言
        for locale in self.to_locales:
            if locale not in updated_locales_dict:
                updated_locales_dict.setdefault(locale, {})
                lg(f"新语言: {locale}")
        # 移除过期语言
        for locale in list(self._locales_dict.keys()):
            if locale not in self.to_locales and locale in updated_locales_dict:
                del updated_locales_dict[locale]
                lg(f"过期语言: {locale}")
        updated_locales_id_dict = self.locales_dict_to_id_dict(updated_locales_dict)
        # 添加新翻译
        for trans_id, sd in str_id_dict.items():
            for locale in updated_locales_dict:
                if trans_id in updated_locales_dict[locale]:
                    continue

                to_be_translated.setdefault(locale, [])
                if sd.string not in to_be_translated[locale]:
                    to_be_translated[locale].append(sd)

                lg(f"新内容: {locale} - {f'{sd.string[:30]}...' if sd.string[30:] else sd.string}")
        # 移除过期翻译
        for locale in updated_locales_id_dict:
            for trans_id in list(updated_locales_id_dict[locale]):
                if trans_id in str_id_dict:
                    continue
                if trans_id not in updated_locales_dict[locale]:
                    continue
                del updated_locales_dict[locale][trans_id]
                lg(f"过期内容: {locale} - {trans_id}")
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

        updated_locale_dict, to_be_translated = self.check_changes(log=False)
        return bool(updated_locale_dict != self._locales_dict or to_be_translated)

    async def item_translate(self, text_id_dict: dict[str, str], to_locale: str) -> dict[str, str]:
        """Translate texts one by one.

        Args:
            text_id_dict: A dictionary of text IDs to texts.
            to_locale: The target language code.

        Returns:
            A dictionary of translated texts keyed by ID.
        """
        result: dict[str, str] = {}
        pbar = self.pbar(to_locale, len(text_id_dict))

        semaphore = asyncio.Semaphore(self.max_concurrency)
        translator = self.translator
        if not isinstance(translator, BaseItemTranslator):
            raise ValueError("错误的翻译器类型")

        async def _translate_one(text: str, locale: str, sem: asyncio.Semaphore) -> str:
            async with sem:
                translated = await translator.translate(text, locale)
                pbar.update()
                return translated

        tasks: dict[str, asyncio.Task] = {
            key: asyncio.create_task(_translate_one(text, to_locale, semaphore)) for key, text in text_id_dict.items()
        }

        done, _ = await asyncio.wait(tasks.values())
        pbar.close()

        for key, task in tasks.items():
            try:
                translated_text = task.result()
            except Exception:
                logger.exception(f"→ [{to_locale}] 翻译失败 (id={key}, text={text_id_dict[key]}):")
            else:
                result[key] = translated_text

        return result

    async def bulk_translation(self, text_id_dict: dict[str, str], to_locale: str) -> dict[str, str]:
        """Translate texts in bulk.

        Args:
            text_id_dict: A dictionary of text IDs to texts.
            to_locale: The target language code.

        Returns:
            A dictionary of translated texts keyed by ID.
        """
        translator = self.translator
        if not isinstance(translator, BaseBulkTranslator):
            raise ValueError("错误的翻译器类型")
        with self.pbar(to_locale, 1) as pbar:
            all_results: dict[str, str] = {}
            items = list(text_id_dict.items())
            for i in range(0, len(items), self.max_concurrency):
                batch = dict(items[i : i + self.max_concurrency])
                batch_results = await translator.translate(batch, to_locale)
                all_results |= batch_results
            pbar.update()
        return all_results

    async def translate(self, text_list: dict[str, str], to_locale: str) -> dict[str, str]:
        if isinstance(self.translator, BaseItemTranslator):
            return await self.item_translate(text_list, to_locale)
        elif isinstance(self.translator, BaseBulkTranslator):
            return await self.bulk_translation(text_list, to_locale)
        else:
            raise ValueError("错误的翻译器类型")

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
    def locales_dict_to_id_dict(locales_dict: dict[str, dict[str, Any]]) -> dict[str, list[str]]:
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

    def pbar(self, locale: str, total: int) -> tqdm:
        try:
            from tqdm import tqdm
        except ImportError as e:
            raise BuildDependencyError() from e

        return tqdm(
            total=total,
            desc=f"⏳ 翻译中 → {locale}",
            unit="条",
            ncols=80,
            bar_format="{desc}: {percentage:3.0f}%|{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}]",
            colour="blue",
            disable=not self.show_progress,
        )
