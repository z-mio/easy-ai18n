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
        i18n_function_names: str | list[str] = None,
        sep: str = None,
        i18n_file_dir: str | Path = None,
    ):
        """
        初始化EasyAI18n实例。
        :param i18n_function_names: 翻译函数的名称
        :param sep: 分隔符, 默认为空格
        :param i18n_file_dir: 翻译文件存放的目录
        """
        self.i18n_function_names = i18n_function_names or ic.i18n_function_names
        self.sep = sep or ic.def_sep
        self.i18n_file_dir = Path(i18n_file_dir) if i18n_file_dir else ic.i18n_dir
        self.i18n_file_dir.mkdir(parents=True, exist_ok=True)

    def build(
        self,
        target_lang: str | list[str],
        project_dir: str | Path = None,
        include: list[str] = None,
        exclude: list[str] = None,
        translator: BaseItemTranslator | BaseBulkTranslator | None = None,
        max_concurrent: int = None,
        disable_progress_bar: bool = False,
    ):
        """
        构建翻译文件
        :param target_lang: 要翻译成的目标语言
        :param project_dir: 需要翻译的项目的根目录
        :param include: 包含的文件或目录
        :param exclude: 排除的文件或目录
        :param translator: 翻译器, 默认为 GoogleTranslator
        :param max_concurrent: 翻译时的并发数
        :param disable_progress_bar: 禁用翻译进度条
        :return:
        """
        return anyio.run(
            self.build_async,
            target_lang,
            project_dir,
            include,
            exclude,
            translator,
            max_concurrent,
            disable_progress_bar,
        )

    async def build_async(
        self,
        target_lang: str | list[str],
        project_dir: str | Path = None,
        include: list[str] = None,
        exclude: list[str] = None,
        translator: BaseItemTranslator | BaseBulkTranslator | None = None,
        max_concurrent: int = None,
        disable_progress_bar: bool = False,
    ):
        """
        异步构建翻译文件
        :param target_lang: 要翻译成的目标语言
        :param project_dir: 需要翻译的项目的根目录
        :param include: 包含的文件或目录
        :param exclude: 排除的文件或目录
        :param translator: 翻译器, 默认为 GoogleTranslator
        :param max_concurrent: 翻译时的并发数
        :param disable_progress_bar: 禁用翻译进度条
        :return:
        """
        builder = Builder(
            target_lang=target_lang,
            i18n_function_names=self.i18n_function_names,
            sep=self.sep,
            project_dir=project_dir,
            i18n_file_dir=self.i18n_file_dir,
            include=include,
            exclude=exclude,
            translator=translator,
            max_concurrent=max_concurrent,
            disable_progress_bar=disable_progress_bar,
        )
        await builder.run()

    def t(
        self,
        global_lang: str = None,
        languages: str | list[str] = None,
        pre_lang_selector: Type[PreLanguageSelector] | None = None,
        post_lang_selector: Type[PostLanguageSelector] | None = None,
    ) -> I18n:
        """
        翻译函数入口
        :param global_lang: 全局默认使用的语言
        :param languages: 要启用的语言, 默认启用全部语言
        :param pre_lang_selector: 前置语言选择器
        :param post_lang_selector: 后置语言选择器
        :return:
        """
        return I18n(
            global_lang=global_lang,
            languages=languages,
            sep=self.sep,
            i18n_file_dir=self.i18n_file_dir,
            i18n_function_names=self.i18n_function_names,
            pre_lang_selector=pre_lang_selector,
            post_lang_selector=post_lang_selector,
        )
