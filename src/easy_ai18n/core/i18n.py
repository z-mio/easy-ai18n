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

    def __init__(self, *, i18n: "I18n", sep: str, locale: str = None):
        self.i18n = i18n
        self.sep = sep
        self.locale = locale

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
        return self.i18n.t(*args, sep=sep or self.sep, frame=frame)[self.locale]


class LocaleContent(str):
    """内容"""

    def __new__(
        cls,
        *,
        text: str,
        locales_dict: dict,
        variables: dict = None,
        locale: str = None,
        post_locale_selector: type["PostLocaleSelector"] | None = None,
    ):
        return str.__new__(cls, text)

    def __init__(
        self,
        *,
        text: str,
        locales_dict: dict,
        variables: dict = None,
        locale: str = None,
        post_locale_selector: type["PostLocaleSelector"] | None = None,
    ):
        self._text = text
        self._locales_dict = locales_dict
        self._variables = variables or {}
        self._locale = locale
        self._post_locale_selector = post_locale_selector or PostLocaleSelector

    def __str__(self) -> str:
        return self.__getitem__(self._locale)

    def __repr__(self) -> str:
        return self.__getitem__(self._locale)

    def __getitem__(self, locale: int | slice | str) -> str:
        """_('内容')[后置语言选择器]"""
        if isinstance(locale, (int, slice)):
            return super().__getitem__(locale)
        return self.__call__(locale)

    def __call__(self, locale: int | slice | str):
        """_('内容')(后置语言选择器)"""
        return str(
            self._post_locale_selector(
                text=self._text,
                locales_dict=self._locales_dict,
                variables=self._variables,
                locale=locale,
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
        locales_dict: dict,
        variables: dict = None,
        locale: str = None,
    ):
        """
        语言选择器，用于选择翻译后的语言
        :param text: 要翻译的文本
        :param variables: 变量字典，用于替换f-string中的变量
        """
        self.text = text
        self.locales_dict = locales_dict
        self.variables = variables or {}
        self.locale = locale

    def __str__(self) -> str:
        return self.__getitem__(self.locale)

    def __repr__(self) -> str:
        return self.__getitem__(self.locale)

    def __getitem__(self, locale: str | None) -> str:
        """_('内容')[后置语言选择器]"""
        return self.format(locale)

    def format(self, locale: str | None = None) -> str:
        """格式化字符串并应用翻译"""
        if not locale:
            return self._format(self.text)
        translated = self.get_by_text(self.text, locale)
        return self._format(translated)

    def _format(self, raw_string: str) -> str:
        for v in self.variables:
            raw_string = raw_string.replace(v, str(self.variables[v]))
        return raw_string

    def get_by_text(self, text: str, locale: str = None):
        return self.locales_dict.get(locale, {}).get(gen_id(text), text)


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
        self.content = LocaleContent
        self.locales_dict = Loader(self.locales_dir).load_locales_file(self.enabled_locales)

    def t(self, *args, sep: str = None, frame: FrameType = None) -> LocaleContent:
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
                locales_dict=self.locales_dict,
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
                locales_dict=self.locales_dict,
                post_locale_selector=self.post_locale_selector,
            )

        # 获取缓存的节点
        call_node = self._cache.get(cache_key, None)

        try:
            result = ASTParser(sep=sep, func_names=self.func_names).extract(frame=f, call_node=call_node)
            return self._handle_cache(original, cache_key, result)
        except Exception:
            logger.exception("I18N解析错误")
            self._parse_failures.add(cache_key)
            return self.content(
                text=original,
                locales_dict=self.locales_dict,
                post_locale_selector=self.post_locale_selector,
            )
        finally:
            del f

    def _handle_cache(self, original: str, cache_key: str, result: StringData) -> LocaleContent:
        """处理缓存并返回结果"""
        if not result:
            self._parse_failures.add(cache_key)
            logger.exception(f"I18N解析错误: {original}")
            return self.content(
                text=original,
                locales_dict=self.locales_dict,
                post_locale_selector=self.post_locale_selector,
            )

        self._cache[cache_key] = result.call_node
        return self.content(
            text=result.string,
            locales_dict=self.locales_dict,
            variables=result.variables,
            locale=self.default_locale,
            post_locale_selector=self.post_locale_selector,
        )

    def clear_cache(self):
        """清除解析缓存"""
        self._cache.clear()
        self._parse_failures.clear()

    def __getitem__(self, locale: str) -> PreLocaleSelector:
        """调用前置语言选择器"""
        return self.pre_locale_selector(i18n=self, locale=locale, sep=self.sep)

    def __call__(self, *args, sep: str = None) -> LocaleContent:
        """调用入口函数"""
        frame = inspect.currentframe().f_back
        return self.t(*args, sep=sep or self.sep, frame=frame)
