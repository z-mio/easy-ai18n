import asyncio
from pathlib import Path

from .config import ic
from .core import (
    Builder,
    I18n,
    PostLocaleSelector,
    PreLocaleSelector,
)
from .translator import BaseBulkTranslator, BaseItemTranslator
from .utils import to_list


class EasyAI18n:
    def __init__(
        self,
        func_names: str | list[str] = None,
        sep: str = None,
        locales_dir: str | Path = None,
    ):
        """
        初始化 EasyAI18n 实例。
        :param func_names: 翻译函数的名称
        :param sep: 分隔符, 默认为空格
        :param locales_dir: 语言文件存放目录
        """
        self.func_names = to_list(func_names) or ic.func_names
        self.sep = sep or ic.sep
        self.locales_dir = Path(locales_dir) if locales_dir else ic.locales_dir
        self.locales_dir.mkdir(parents=True, exist_ok=True)

    def build(
        self,
        to_locales: str | list[str],
        project_root: str | Path = None,
        include: list[str] = None,
        exclude: list[str] = None,
        translator: BaseItemTranslator | BaseBulkTranslator | None = None,
        max_concurrency: int = None,
        show_progress: bool = True,
    ):
        """
        构建翻译文件
        :param to_locales: 要翻译到的目标语言
        :param project_root: 项目根目录
        :param include: 包含的文件或目录
        :param exclude: 排除的文件或目录
        :param translator: 翻译器, 默认为 GoogleTranslator
        :param max_concurrency: 翻译时的最大并发数
        :param show_progress: 是否显示翻译进度条
        :return:
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
        project_root: str | Path = None,
        include: list[str] = None,
        exclude: list[str] = None,
        translator: BaseItemTranslator | BaseBulkTranslator | None = None,
        max_concurrency: int = None,
        show_progress: bool = True,
    ):
        """
        异步构建翻译文件
        :param to_locales: 要翻译到的目标语言
        :param project_root: 项目根目录
        :param include: 包含的文件或目录
        :param exclude: 排除的文件或目录
        :param translator: 翻译器, 默认为 GoogleTranslator
        :param max_concurrency: 翻译时的最大并发数
        :param show_progress: 是否显示翻译进度条
        :return:
        """
        builder = Builder(
            to_locales=to_list(to_locales),
            sep=self.sep,
            func_names=self.func_names,
            project_root=project_root,
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
        default_locale: str = None,
        enabled_locales: str | list[str] = None,
        pre_locale_selector: type[PreLocaleSelector] | None = None,
        post_locale_selector: type[PostLocaleSelector] | None = None,
    ) -> I18n:
        """
        翻译函数入口
        :param default_locale: 默认使用的语言
        :param enabled_locales: 要启用的语言, 默认启用全部语言
        :param pre_locale_selector: 前置语言选择器
        :param post_locale_selector: 后置语言选择器
        :return:
        """
        return I18n(
            default_locale=default_locale,
            enabled_locales=to_list(enabled_locales),
            sep=self.sep,
            locales_dir=self.locales_dir,
            func_names=self.func_names,
            pre_locale_selector=pre_locale_selector,
            post_locale_selector=post_locale_selector,
        )
