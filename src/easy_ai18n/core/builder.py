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
from tqdm import tqdm
from .loader import Loader
from .parser import ASTParser
from ..config import ic
from ..translator import GoogleTranslator, BaseItemTranslator, BaseBulkTranslator
from ..log import logger
from ..utiles import gen_id, to_list, to_path


class Builder:
    def __init__(
        self,
        target_lang: str | list[str] = "en",
        sep: str = None,
        i18n_function_names: str | list[str] = None,
        project_dir: str = None,
        i18n_file_dir: str | Path = None,
        include: list[str] = None,
        exclude: list[str] = None,
        translator: BaseItemTranslator | BaseBulkTranslator | None = None,
        disable_progress_bar: bool = False,
        max_concurrent: int = None,
    ):
        """
        初始化Builder
        :param target_lang: 目标语言
        :param sep: 分隔符
        :param i18n_function_names: 翻译函数名
        :param project_dir: 需要翻译的项目的根目录
        :param i18n_file_dir: 翻译文件目录
        :param include: 包含的文件或目录
        :param exclude: 排除的文件或目录
        :param translator: 翻译器, 默认为 GoogleTranslator
        :param disable_progress_bar: 禁用翻译进度条
        :param max_concurrent: 翻译时的并发数
        """
        self.project_dir = to_path(project_dir) or Path(os.getcwd())
        self.include = include or []
        self.exclude = exclude or []
        self.default_exclude = [".venv", "venv", ".git", ".idea"]
        self.i18n_function_names = (
            to_list(i18n_function_names) or ic.i18n_function_names
        )
        self.sep = sep or ic.def_sep
        self.target_lang = to_list(target_lang)
        self.i18n_file_dir = to_path(i18n_file_dir) or ic.i18n_dir
        self.translator = translator or GoogleTranslator()

        self.project_files = self.load_file()
        self.disable_progress_bar = disable_progress_bar
        self.max_concurrent = max_concurrent or (
            30 if isinstance(self.translator, BaseItemTranslator) else 50
        )
        self._i18n_dict = Loader(self.i18n_file_dir).load_i18n_file(self.target_lang)

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
        updated_i18n_dict, to_be_translated = self.check_chage()
        for lang, str_set in to_be_translated.items():
            try:
                i18n_dict = await self.translate(list(str_set), lang)
            except Exception:
                logger.exception(f"翻译到 {lang} 失败:")
            else:
                updated_i18n_dict.setdefault(lang, {})
                updated_i18n_dict[lang] |= i18n_dict

        if save_to_file:
            for lang in updated_i18n_dict:
                self.save_to_yaml(updated_i18n_dict[lang], lang)
        return True

    def check_chage(self, log: bool = True) -> tuple[dict, dict]:
        """
        检查差异
        :return: 移除过期翻译后的字典, 新增内容字典
        """
        lg = logger.debug if log else lambda x: None
        str_id_dict = {}
        for file in self.project_files:
            for text in self.extract_strings(file):
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
        project_files = []
        include_paths = [Path(p) for p in self.include] if self.include else []
        exclude_paths = [Path(p) for p in self.exclude]

        for root, dirs, files in self.project_dir.walk():
            # 先做目录排除
            dirs[:] = [
                d
                for d in dirs
                if not any(
                    (Path(root) / d).relative_to(self.project_dir).match(str(exc))
                    for exc in self.default_exclude + exclude_paths
                )
            ]
            for fname in files:
                if not fname.endswith(".py"):
                    continue

                full = Path(root) / fname
                rel = full.relative_to(self.project_dir)

                if include_paths:
                    if not any(str(rel).startswith(str(ip)) for ip in include_paths):
                        continue

                if any(str(rel).startswith(str(ep)) for ep in exclude_paths):
                    continue

                project_files.append(full)

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

    async def item_translate(
        self, text_list: list[str], target_lang: str = None
    ) -> dict[str, str]:
        """
        逐条翻译
        :param text_list: 待翻译的字符串列表
        :param target_lang: 目标语言
        :return: 翻译后的字典 {lang: {id: translated_text}}
        """
        result = {}
        pbar = self.pbar(target_lang, len(text_list))

        async def _fn(text_, lang_, semaphore_):
            async with semaphore_:
                tr = await self.translator.translate(text_, lang_)
                pbar.update()
                return tr

        # 最大并发数
        semaphore = anyio.Semaphore(self.max_concurrent)
        async with anyio.create_task_group() as tg:
            results = {
                text: ResultCapture.start_soon(
                    tg,  # type: ignore
                    _fn,
                    text,
                    target_lang,
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
            except TaskFailedException:
                logger.exception(f"→ [{target_lang}]翻译失败内容: {i} | 错误详情:")
            else:
                result[gen_id(i)] = r.result()
        return result

    async def bulk_translation(
        self, text_list: list[str], target_lang: str = None
    ) -> dict[str, str]:
        """
        整体翻译
        :param text_list:
        :param target_lang:
        :return:
        """
        text_id_dict = {gen_id(text): text for text in text_list}
        with self.pbar(target_lang, 1) as pbar:
            all_results = {}
            items = list(text_id_dict.items())
            for i in range(0, len(items), self.max_concurrent):
                batch = dict(items[i : i + self.max_concurrent])
                batch_results = await self.translator.translate(batch, target_lang)
                all_results |= batch_results
            pbar.update()
        return all_results

    async def translate(
        self, text_list: list[str], target_lang: str = None
    ) -> dict[str, str]:
        if isinstance(self.translator, BaseItemTranslator):
            return await self.item_translate(text_list, target_lang)
        elif isinstance(self.translator, BaseBulkTranslator):
            return await self.bulk_translation(text_list, target_lang)
        else:
            raise ValueError("translation_mode 必须是 'item' 或 'bulk'")

    def extract_strings(self, file: Path) -> list[str]:
        """
        从文件中提取出所有需要翻译的字符串
        :param file: 文件路径
        :return:
        """
        module = ast.parse(file.read_text(encoding="utf-8"))
        return ASTParser(
            sep=self.sep, i18n_function_names=self.i18n_function_names
        ).extract_all(node=module)

    def save_to_yaml(self, i18n_dict: dict, lang: str):
        """
        将翻译结果输出到文件
        :param i18n_dict: 翻译结果字典
        :param lang: 目标语言
        :return:
        """
        with open(self.i18n_file_dir / f"{lang}.yaml", "w", encoding="utf-8") as f:
            yaml.dump(i18n_dict, f, allow_unicode=True)

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
