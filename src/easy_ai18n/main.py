from pathlib import Path
from typing import Type

import anyio

from .config import ic
from .core import (
    I18n,
    Builder,
    PreLanguageSelector,
    PostLanguageSelector,
)
from .translator import BaseItemTranslator, BaseBulkTranslator


class EasyAI18n:
    def __init__(
        self,
        global_lang: str = None,
        target_lang: str | list[str] = None,
        languages: str | list[str] = None,
        project_dir: str | Path = None,
        include: list[str] = None,
        exclude: list[str] = None,
        i18n_file_dir: str | Path = None,
        func_name: str | list[str] = None,
        sep: str = None,
        translator: BaseItemTranslator | BaseBulkTranslator | None = None,
        pre_lang_selector: Type[PreLanguageSelector] | None = None,
        post_lang_selector: Type[PostLanguageSelector] | None = None,
    ):
        """
        初始化EasyAI18n实例。

        :param global_lang: 全局默认使用的语言
        :param target_lang: 要翻译成的目标语言
        :param languages: 要启用的语言, 默认使用目标语言
        :param project_dir: 需要翻译的项目的根目录
        :param include: 包含的文件或目录
        :param exclude: 排除的文件或目录
        :param i18n_file_dir: 翻译文件存放的目录
        :param func_name: 翻译函数的名称
        :param sep: 分隔符, 默认为空格
        :param translator: 翻译器, 默认为 GoogleTranslator
        :param pre_lang_selector: 前置语言选择器
        :param post_lang_selector: 后置语言选择器
        """
        self.global_lang = global_lang
        self.target_lang = target_lang
        self.languages = languages or self.target_lang
        self.project_dir = project_dir
        self.include = include
        self.exclude = exclude
        self.i18n_file_dir = Path(i18n_file_dir) if i18n_file_dir else ic.i18n_dir
        self.func_name = func_name or ic.i18n_function_name
        self.sep = sep or ic.def_sep
        self.translator = translator
        self.pre_lang_selector = pre_lang_selector
        self.post_lang_selector = post_lang_selector

        self._init_config()

    def _init_config(self):
        """
        初始化配置
        :return:
        """
        ic.i18n_function_name = self.func_name
        ic.i18n_dir = self.i18n_file_dir
        ic.def_sep = self.sep

        self.i18n_file_dir.mkdir(parents=True, exist_ok=True)

    def build(self, max_concurrent: int = None, disable_progress_bar: bool = False):
        """
        构建翻译文件
        :param max_concurrent: 翻译时的并发数
        :param disable_progress_bar: 禁用翻译进度条
        :return:
        """
        return anyio.run(self.build_async, max_concurrent, disable_progress_bar)

    async def build_async(
        self, max_concurrent: int = None, disable_progress_bar: bool = False
    ):
        """
        异步构建翻译文件
        :param max_concurrent: 翻译时的并发数
        :param disable_progress_bar: 禁用翻译进度条
        :return:
        """
        builder = Builder(
            target_lang=self.target_lang,
            project_dir=self.project_dir,
            include=self.include,
            exclude=self.exclude,
            translator=self.translator,
            max_concurrent=max_concurrent,
            disable_progress_bar=disable_progress_bar,
        )
        await builder.run()
        del builder  # 释放内存

    def t(self) -> I18n:
        """
        翻译入口
        :return:
        """
        return I18n(
            global_lang=self.global_lang,
            languages=self.target_lang,
            pre_lang_selector=self.pre_lang_selector,
            post_lang_selector=self.post_lang_selector,
        )
