"""
翻译字典构建器
"""

import ast
import os
from pathlib import Path
import copy

import anyio
import yaml
from aioresult import ResultCapture, TaskFailedException
from tenacity import RetryError
from tqdm import tqdm
from .loader import Loader
from .parser import ASTParser
from ..config import ic
from ..error import BuildedError
from ..translator import GoogleTranslator, BaseItemTranslator, BaseBulkTranslator
from ..log import logger

from ..utiles import gen_id


class Builder:
    def __init__(
        self,
        target_lang: str | list[str] = "en",
        project_dir: str = None,
        include: list[str] = None,
        exclude: list[str] = None,
        translator: BaseItemTranslator | BaseBulkTranslator | None = None,
        disable_progress_bar: bool = False,
        max_concurrent: int = None,
    ):
        """
        初始化Builder
        :param target_lang: 目标语言
        :param project_dir: 需要翻译的项目的根目录
        :param include: 包含的文件或目录
        :param exclude: 排除的文件或目录
        :param translator: 翻译器, 默认为 GoogleTranslator
        :param disable_progress_bar: 禁用翻译进度条
        :param max_concurrent: 翻译时的并发数
        """
        self.project_dir = (
            Path(os.getcwd()) if project_dir is None else Path(project_dir)
        )
        self.include = include or []
        self.exclude = exclude or []
        self.default_exclude = [".venv", "venv", ".git", ".idea"]
        self.func_name = ic.i18n_function_name
        self.target_lang = (
            target_lang if isinstance(target_lang, list) else [target_lang]
        )
        self.translator = translator or GoogleTranslator()

        self.project_files = self.load_file()
        self.disable_progress_bar = disable_progress_bar
        self.max_concurrent = max_concurrent or 30
        self._i18n_dict = Loader.load_i18n_file(self.target_lang)

    async def run(self) -> None:
        try:
            if not self.is_changed():
                return
            logger.info("内容有更新, 开始更新翻译内容...")
            translated_dict = await self.build_project()
            self.output_dict_to_yaml(translated_dict)
            return
        except Exception as e:
            raise BuildedError(f"构建失败: {e}")

    async def build_project(self) -> dict:
        """
        构建整个项目的翻译字典
        :return: i18n_dict: {zh: {id: translated_text}, en: {id: translated_text}}
        """

        updated_i18n_dict, to_be_translated = self.check_chage()
        new_i18n_dict = [
            await self.translate(list(str_set), lang)
            for lang, str_set in to_be_translated.items()
        ]
        i18n_dict = {}
        for d in new_i18n_dict:
            i18n_dict |= d
        for lang in i18n_dict:
            updated_i18n_dict.setdefault(lang, {})
            updated_i18n_dict[lang] |= i18n_dict[lang]
        return updated_i18n_dict

    def check_chage(self, log: bool = True) -> tuple[dict, dict]:
        """
        检查差异
        :return: 移除过期翻译后的字典, 待翻译字典
        """
        lg = logger.debug if log else lambda x: None
        str_id_dict = {}
        for file in self.project_files:
            for text in self.extract_translatable_strings_by_file(file):
                if not text:
                    continue
                str_id_dict[gen_id(text)] = text

        updated_i18n_dict = copy.deepcopy(self._i18n_dict)
        to_be_translated: dict[str, set[str]] = {}
        # 添加新语言
        for lang in self.target_lang:
            if lang not in updated_i18n_dict:
                updated_i18n_dict.setdefault(lang, {})
                lg(f"新语言: {lang}")
        # 移除过期语言
        for lang in list(self._i18n_dict.keys()):
            if lang not in self.target_lang:
                if lang in updated_i18n_dict:
                    del updated_i18n_dict[lang]
                    lg(f"过期语言: {lang}")
        updated_i18n_id_dict = self.i18n_dict_to_id_dict(updated_i18n_dict)
        # 添加新翻译
        for trans_id, orig_text in str_id_dict.items():
            for lang in updated_i18n_dict:
                if trans_id in updated_i18n_dict[lang]:
                    continue
                to_be_translated.setdefault(lang, set()).add(orig_text)
                lg(
                    f"新内容: {lang} - {f'{orig_text[:30]}...' if orig_text[30:] else orig_text}"
                )
        # 移除过期翻译
        for lang in updated_i18n_id_dict:
            for trans_id in list(updated_i18n_id_dict[lang]):
                if trans_id in str_id_dict:
                    continue
                if trans_id not in updated_i18n_dict[lang]:
                    continue
                del updated_i18n_dict[lang][trans_id]
                lg(f"过期内容: {lang} - {trans_id}")
        return updated_i18n_dict, to_be_translated

    def load_file(self):
        """
        加载项目文件：
        - include 列表非空时，只采纳 include 中指定的文件或目录下的 .py 文件；
        - include 为空时，先剔除 default_exclude，再根据 exclude 列表过滤；
        :return: List[Path]，项目中符合条件的 .py 文件路径
        """
        project_files = []

        if self.include:
            include_files = {name for name in self.include if name.endswith(".py")}
            include_dirs = {name for name in self.include if not name.endswith(".py")}
        else:
            include_files = set()
            include_dirs = set()

        for root, dirs, files in self.project_dir.walk():
            dirs[:] = [d for d in dirs if d not in self.default_exclude]

            if not self.include:
                dirs[:] = [d for d in dirs if d not in self.exclude]

            for fname in files:
                if not fname.endswith(".py"):
                    continue

                full_path = Path(root) / fname
                rel_parts = full_path.relative_to(self.project_dir).parts

                if self.include:
                    in_file_list = fname in include_files
                    in_dir_list = bool(rel_parts and rel_parts[0] in include_dirs)
                    if in_file_list or in_dir_list:
                        project_files.append(full_path)
                else:
                    if fname not in self.exclude:
                        project_files.append(full_path)

        return project_files

    def is_changed(self) -> bool:
        """
        判断翻译字典是否有更新
        :return:
        """

        updated_i18n_dict, to_be_translated = self.check_chage(log=False)
        if updated_i18n_dict != self._i18n_dict or to_be_translated:
            return True
        return False

    async def build_single_file(self, file: str | Path) -> dict:
        """
        构建单个文件的翻译字典
        :param file: 文件路径
        :return: i18n_dict: {zh: {id: translated_text}, en: {id: translated_text}}
        """
        file = Path(file)
        translatable_strings = self.extract_translatable_strings_by_file(file)
        i18n_dict = await self.translate(translatable_strings)
        return i18n_dict

    async def item_translate(
        self, text_list: list[str], target_lang: str | list[str] = None
    ) -> dict[str, dict[str, str]]:
        """
        逐条翻译
        :param text_list: 待翻译的字符串列表
        :param target_lang: 目标语言
        :return: 翻译后的字典 {lang: {id: translated_text}}
        """
        i18n_dict = {}

        for lang in target_lang:
            i18n_dict.setdefault(lang, {})
            pbar = self.pbar(lang, len(text_list))

            async def _fn(text_, lang_, semaphore_):
                async with semaphore_:
                    result = await self.translator.translate(text_, lang_)
                    pbar.update()
                    return result

            # 最大并发数
            semaphore = anyio.Semaphore(self.max_concurrent)
            async with anyio.create_task_group() as tg:
                results = {
                    text: ResultCapture.start_soon(
                        tg,  # type: ignore
                        _fn,
                        text,
                        lang,
                        semaphore,
                        suppress_exception=True,
                    )
                    for text in text_list
                }
            pbar.close()
            for i, r in results.items():
                r: ResultCapture
                try:
                    r.result()
                except TaskFailedException as e:
                    retry_error: RetryError = e.args[0].exception()
                    e = retry_error.last_attempt.exception()
                    logger.error(f"→ [{lang}]翻译失败: {i}\n错误详情: {e}")
                else:
                    i18n_dict[lang][gen_id(i)] = r.result()
        return i18n_dict

    async def bulk_translation(
        self, text_list: list[str], target_lang: str | list[str] = None
    ) -> dict[str, dict[str, str]]:
        """
        整体翻译
        :param text_list:
        :param target_lang:
        :return:
        """
        i18n_dict = {}
        text_id_dict = {gen_id(text): text for text in text_list}
        for lang in target_lang:
            with self.pbar(lang, 1) as pbar:
                i18n_dict[lang] = await self.translator.translate(text_id_dict, lang)
                pbar.update()
        return i18n_dict

    async def translate(
        self, text_list: list[str], target_lang: str | list[str] = None
    ) -> dict[str, dict[str, str]]:
        target_lang = (
            target_lang and target_lang
            if isinstance(target_lang, list)
            else [target_lang]
        ) or self.target_lang

        if isinstance(self.translator, BaseItemTranslator):
            return await self.item_translate(text_list, target_lang)
        elif isinstance(self.translator, BaseBulkTranslator):
            return await self.bulk_translation(text_list, target_lang)
        else:
            raise ValueError("translation_mode must be 'item' or 'bulk'")

    @staticmethod
    def extract_translatable_strings_by_file(file: Path) -> list[str]:
        """
        从文件中提取出所有需要翻译的字符串
        :param file: 文件路径
        :return:
        """
        module = ast.parse(file.read_text(encoding="utf-8"))
        return ASTParser().extract_all_strings(node=module)

    @staticmethod
    def load_i18n_file() -> dict:
        """
        加载i18n目录下的yaml文件
        :return: i18n字典
        """
        i18n_dict = {}
        i18n_files = ic.i18n_dir.glob("**/*.yaml")
        if not i18n_files:
            return {}
        for file in i18n_files:
            file = Path(file)
            yaml.safe_load(Path(file).read_text(encoding="utf-8"))
            i18n_dict[file.name.split(".")[0]] = yaml.safe_load(
                file.read_text(encoding="utf-8")
            )
        return i18n_dict

    @staticmethod
    def output_dict_to_yaml(translated_dict: dict):
        """
        将翻译结果输出到文件
        :param translated_dict: 翻译结果字典
        :return:
        """
        [os.remove(i) for i in ic.i18n_dir.glob("**/*.yaml")]
        for lang in translated_dict:
            with open(ic.i18n_dir / f"{lang}.yaml", "w", encoding="utf-8") as f:
                yaml.dump(translated_dict[lang], f, allow_unicode=True)

    @staticmethod
    def i18n_dict_to_id_dict(i18n_dict: dict) -> dict[str, list[str]]:
        """
        获取i18n字典中的所有id
        :return:
        """

        if not i18n_dict:
            return {}

        i18n_id_dict = i18n_dict.copy()
        for lang in i18n_id_dict:
            i18n_id_dict[lang] = [k for k in i18n_id_dict[lang]]
        return i18n_id_dict

    def pbar(self, lang: str, total: int):
        return tqdm(
            total=total,
            desc=f"⏳ 翻译中 → {lang}",
            unit="条",
            ncols=80,
            bar_format="{desc}: {percentage:3.0f}%|{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}]",
            colour="blue",
            disable=self.disable_progress_bar,
        )
