"""
翻译函数, 语言选择器
"""

import inspect
import sys
from pathlib import Path
from types import FrameType
from typing import TYPE_CHECKING

from ..config import ic
from ..log import logger
from ..utils import gen_id
from .loader import Loader
from .parser import ASTParser, StringData

if TYPE_CHECKING:
    import ast


class PreLocaleSelector:
    """前置语言选择器"""

    def __init__(self, *, i18n: "I18n", sep: str, lang: str = None):
        self.i18n = i18n
        self.lang = lang
        self.sep = sep

    def __str__(self) -> str:
        return ""

    def __repr__(self) -> str:
        return ""

    def __call__(self, *args, sep: str = None) -> str:
        """
        调用后置语言选择器
        _[前置语言选择器]('内容')
        :param args: 要翻译的文本
        :param sep: 分隔符
        :return:
        """
        frame = inspect.currentframe().f_back
        return self.i18n.t(*args, sep=sep or self.sep, frame=frame)[self.lang]


class I18nContent(str):
    """内容"""

    def __new__(
        cls,
        *,
        text: str,
        i18n_dict: dict,
        variables: dict = None,
        lang: str = None,
        post_locale_selector: type["PostLocaleSelector"] | None = None,
    ):
        return str.__new__(cls, text)

    def __init__(
        self,
        *,
        text: str,
        i18n_dict: dict,
        variables: dict = None,
        lang: str = None,
        post_locale_selector: type["PostLocaleSelector"] | None = None,
    ):
        self._text = text
        self._variables = variables or {}
        self._lang = lang
        self._post_locale_selector = post_locale_selector or PostLocaleSelector
        self._i18n_dict = i18n_dict

    def __str__(self) -> str:
        return self.__getitem__(self._lang)

    def __repr__(self) -> str:
        return self.__getitem__(self._lang)

    def __getitem__(self, lang: int | slice | any) -> str:
        """_('内容')[后置语言选择器]"""
        if isinstance(lang, (int, slice)):
            return super().__getitem__(lang)
        return self.__call__(lang)

    def __call__(self, lang: int | slice | any):
        """_('内容')(后置语言选择器)"""
        return str(
            self._post_locale_selector(
                text=self._text,
                i18n_dict=self._i18n_dict,
                variables=self._variables,
                lang=lang,
            )
        )

    def __int__(self):
        return int(self.__str__())


class PostLocaleSelector:
    """后置语言选择器"""

    def __init__(
        self,
        *,
        text: str,
        i18n_dict: dict,
        variables: dict = None,
        lang: str = None,
    ):
        """
        语言选择器，用于选择翻译后的语言
        :param text: 要翻译的文本
        :param variables: 变量字典，用于替换f-string中的变量
        """
        self.text = text
        self.variables = variables or {}
        self.lang = lang
        self.i18n_dict = i18n_dict

    def __str__(self) -> str:
        return self.__getitem__(self.lang)

    def __repr__(self) -> str:
        return self.__getitem__(self.lang)

    def __getitem__(self, key: str | None) -> str:
        """_('内容')[后置语言选择器]"""
        return self.format(key)

    def format(self, lang: str | None = None) -> str:
        """格式化字符串并应用翻译"""
        if not lang:
            return self._format(self.text)
        translated = self.get_by_text(self.text, lang)
        return self._format(translated)

    def _format(self, raw_string) -> str:
        for v in self.variables:
            raw_string = raw_string.replace(v, str(self.variables[v]))
        return raw_string

    def get_by_text(self, text: str, lang: str = None):
        return self.i18n_dict.get(lang, {}).get(gen_id(text), text)


class I18n:
    def __init__(
        self,
        enabled_locales: list[str] = None,
        default_locale: str = None,
        sep: str = None,
        locales_dir: str | Path = None,
        func_names: list[str] = None,
        pre_locale_selector: type[PreLocaleSelector] | None = None,
        post_locale_selector: type[PostLocaleSelector] | None = None,
    ):
        """
        初始化I18n
        :param enabled_locales: 要启用的语言
        :param default_locale: 默认使用的语言
        :param sep: 字符串分隔符
        :param func_names: 翻译函数名
        :param pre_locale_selector: 前置语言选择器类
        :param post_locale_selector: 后置语言选择器类
        """
        self._cache: dict[str, ast.Call] = {}
        self._parse_failures: set[str] = set()

        self.default_locale = default_locale
        self.enabled_locales = enabled_locales
        if self.enabled_locales and self.default_locale not in self.enabled_locales:
            self.enabled_locales.append(self.default_locale)

        self.sep = sep or ic.def_sep
        self.locales_dir = locales_dir or ic.i18n_dir
        self.func_names = func_names or ic.func_names
        self.pre_locale_selector = pre_locale_selector or PreLocaleSelector
        self.post_locale_selector = post_locale_selector or PostLocaleSelector
        self.content = I18nContent
        self.i18n_dict = Loader(self.locales_dir).load_i18n_file(self.enabled_locales)

    def t(self, *args, sep: str = None, frame: FrameType = None) -> I18nContent:  # type: ignore
        """
        入口函数

        Args:
            sep: 字符串分隔符，默认为空格
            frame: 调用者的栈帧，默认使用当前栈帧

        Returns:
            PostLanguageSelector 对象
        """
        sep = sep or self.sep
        original = sep.join([str(item) for item in args])
        f = frame or sys._getframe(1)
        if not f:
            return self.content(
                text=original,
                i18n_dict=self.i18n_dict,
                post_locale_selector=self.post_locale_selector,
            )
        positions = (
            f.f_lineno,
            f.f_lasti,
            f.f_code.co_name,
            f.f_code.co_filename,
        )
        cache_key = gen_id(positions)

        # 解析错误的内容直接返回原文
        if cache_key in self._parse_failures:
            return self.content(
                text=original,
                i18n_dict=self.i18n_dict,
                post_locale_selector=self.post_locale_selector,
            )

        # 获取缓存的节点
        call_node = self._cache.get(cache_key, None)

        try:
            result = ASTParser(sep=sep, i18n_function_names=self.func_names).extract(frame=f, call_node=call_node)
            return self._handle_cache(original, cache_key, result)
        except Exception:
            logger.exception("I18N解析错误")
            self._parse_failures.add(cache_key)
            return self.content(
                text=original,
                i18n_dict=self.i18n_dict,
                post_locale_selector=self.post_locale_selector,
            )
        finally:
            # noinspection PyInconsistentReturns
            del f

    def _handle_cache(self, original: str, cache_key: str, result: StringData) -> I18nContent:
        """处理缓存并返回结果"""
        if not result:
            self._parse_failures.add(cache_key)
            logger.exception(f"I18N解析错误: {original}")
            return self.content(
                text=original,
                i18n_dict=self.i18n_dict,
                post_locale_selector=self.post_locale_selector,
            )

        self._cache[cache_key] = result.call_node
        return self.content(
            text=result.string,
            i18n_dict=self.i18n_dict,
            variables=result.variables,
            lang=self.default_locale,
            post_locale_selector=self.post_locale_selector,
        )

    def clear_cache(self):
        """清除解析缓存"""
        self._cache.clear()
        self._parse_failures.clear()

    def __getitem__(self, lang: str) -> PreLocaleSelector:
        """调用前置语言选择器"""
        return self.pre_locale_selector(i18n=self, lang=lang, sep=self.sep)

    def __call__(self, *args, sep: str = None) -> I18nContent:
        """调用入口函数"""
        frame = inspect.currentframe().f_back
        return self.t(*args, sep=sep or self.sep, frame=frame)
