"""
翻译字典构建器
"""

import ast
import asyncio
import copy
import os
from pathlib import Path

import yaml
from tqdm import tqdm

from ..config import ic
from ..log import logger
from ..translator import BaseBulkTranslator, BaseItemTranslator, GoogleTranslator
from ..utils import gen_id, to_path
from .loader import Loader
from .parser import ASTParser, StringData


class Builder:
    def __init__(
        self,
        to_locales: list[str] = None,
        sep: str = None,
        func_names: list[str] = None,
        project_root: str = None,
        locales_dir: str | Path = None,
        include: list[str] = None,
        exclude: list[str] = None,
        translator: BaseItemTranslator | BaseBulkTranslator | None = None,
        show_progress: bool = True,
        max_concurrency: int = None,
    ):
        """
        初始化Builder
        :param to_locales: 要翻译到的目标语言
        :param sep: 分隔符
        :param func_names: 翻译函数名
        :param project_root: 项目根目录
        :param locales_dir: 语言文件目录
        :param include: 包含的文件或目录
        :param exclude: 排除的文件或目录
        :param translator: 翻译器, 默认为 GoogleTranslator
        :param show_progress: 是否显示翻译进度条
        :param max_concurrency: 翻译时的最大并发数
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
        self.translator = translator or GoogleTranslator()

        self.project_files = self.load_file()
        self.show_progress = show_progress
        self.max_concurrency = max_concurrency or (30 if isinstance(self.translator, BaseItemTranslator) else 50)
        self._locales_dict = Loader(self.locales_dir).load_locales_file(self.to_locales)

    async def run(self) -> None:
        if not self.is_changed():
            return logger.info("内容无更新")

        logger.info("内容有更新, 开始更新...")
        if await self.build():
            return logger.success("更新完成")
        else:
            return logger.exception("构建失败:")

    async def build(self, save_to_file: bool = True) -> bool:
        """
        构建翻译字典
        :param save_to_file: 是否保存到文件
        :return:
        """
        updated_locales_dict, to_be_translated = self.check_chage()

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

    def check_chage(self, log: bool = True) -> tuple[dict[str, dict], dict[str, list[StringData]]]:
        """
        检查差异
        :return: 移除过期翻译后的字典, 新增内容字典
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

    def load_file(self):
        project_files = []
        include_paths = [Path(p) for p in self.include] if self.include else []
        exclude_paths = [Path(p) for p in self.exclude]

        for root, dirs, files in self.project_root.walk():
            # 先做目录排除
            dirs[:] = [
                d
                for d in dirs
                if not any((Path(root) / d).relative_to(self.project_root).match(str(exc)) for exc in self.default_exclude + exclude_paths)
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
        """
        判断 locales 字典是否有更新
        :return:
        """

        updated_locale_dict, to_be_translated = self.check_chage(log=False)
        return bool(updated_locale_dict != self._locales_dict or to_be_translated)

    async def item_translate(self, text_id_dict: dict[str, str], to_locale: str = None) -> dict[str, str]:
        """
        逐条翻译
        :param text_id_dict: 待翻译的字符串字典 {id: text}
        :param to_locale: 目标语言
        :return: 翻译后的字典 {id: translated_text}
        """
        result: dict[str, str] = {}
        pbar = self.pbar(to_locale, len(text_id_dict))

        semaphore = asyncio.Semaphore(self.max_concurrency)

        async def _translate_one(text: str, locale: str, sem: asyncio.Semaphore) -> str:
            async with sem:
                translated = await self.translator.translate(text, locale)
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

    async def bulk_translation(self, text_id_dict: dict[str, str], to_locale: str = None) -> dict[str, str]:
        """
        整体翻译
        :param text_id_dict:
        :param to_locale:
        :return:
        """
        with self.pbar(to_locale, 1) as pbar:
            all_results = {}
            items = list(text_id_dict.items())
            for i in range(0, len(items), self.max_concurrency):
                batch = dict(items[i : i + self.max_concurrency])
                batch_results = await self.translator.translate(batch, to_locale)
                all_results |= batch_results
            pbar.update()
        return all_results

    async def translate(self, text_list: dict[str, str], to_locale: str = None) -> dict[str, str]:
        if isinstance(self.translator, BaseItemTranslator):
            return await self.item_translate(text_list, to_locale)
        elif isinstance(self.translator, BaseBulkTranslator):
            return await self.bulk_translation(text_list, to_locale)
        else:
            raise ValueError("错误的翻译器类型")

    def extract_strings(self, file: Path) -> list[StringData]:
        """
        从文件中提取出所有需要翻译的字符串
        :param file: 文件路径
        :return:
        """
        module = ast.parse(file.read_text(encoding="utf-8"))
        return ASTParser(sep=self.sep, func_names=self.func_names).extract_all(node=module)

    def save_to_yaml(self, locale_dict: dict, locale: str):
        """
        将翻译结果输出到文件
        :param locale_dict: 翻译结果字典
        :param locale: 目标语言
        :return:
        """
        with open(self.locales_dir / f"{locale}.yaml", "w", encoding="utf-8") as f:
            yaml.dump(locale_dict, f, allow_unicode=True)

    @staticmethod
    def locales_dict_to_id_dict(locales_dict: dict) -> dict[str, list[str]]:
        """
        获取 locales 字典中的所有id
        :return:
        """

        if not locales_dict:
            return {}

        locales_id_dict = locales_dict.copy()
        for locale in locales_id_dict:
            locales_id_dict[locale] = list(locales_id_dict[locale])
        return locales_id_dict

    def pbar(self, locale: str, total: int):
        return tqdm(
            total=total,
            desc=f"⏳ 翻译中 → {locale}",
            unit="条",
            ncols=80,
            bar_format="{desc}: {percentage:3.0f}%|{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}]",
            colour="blue",
            disable=not self.show_progress,
        )
