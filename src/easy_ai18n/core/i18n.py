"""
翻译函数, 语言选择器
"""

import abc
import ast
import inspect
import sys
from pathlib import Path
from types import FrameType
from typing import Type, Union

from .loader import Loader
from .parser import ASTParser, StringData
from ..config import ic
from ..log import logger
from ..utiles import gen_id, to_list


class PreLanguageSelector(abc.ABC):
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
        post_lang_selector: Type["PostLanguageSelector"] | None = None,
    ):
        return str.__new__(cls, text)

    def __init__(
        self,
        *,
        text: str,
        i18n_dict: dict,
        variables: dict = None,
        lang: str = None,
        post_lang_selector: Type["PostLanguageSelector"] | None = None,
    ):
        self._text = text
        self._variables = variables or {}
        self._lang = lang
        self._post_lang_selector = post_lang_selector or PostLanguageSelector
        self._i18n_dict = i18n_dict

    def __str__(self) -> str:
        return self.__getitem__(self._lang)

    def __repr__(self) -> str:
        return self.__getitem__(self._lang)

    def __getitem__(self, lang: Union[int, slice, any]) -> str:
        """_('内容')[后置语言选择器]"""
        if isinstance(lang, (int, slice)):
            return super().__getitem__(lang)
        return self.__call__(lang)

    def __call__(self, lang: Union[int, slice, any]):
        """_('内容')(后置语言选择器)"""
        return str(
            self._post_lang_selector(
                text=self._text,
                i18n_dict=self._i18n_dict,
                variables=self._variables,
                lang=lang,
            )
        )

    def __int__(self):
        return int(self.__str__())


class PostLanguageSelector(abc.ABC):
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
        languages: str | list[str] = None,
        global_lang: str = None,
        sep: str = None,
        i18n_file_dir: str | Path = None,
        i18n_function_names: str | list[str] = None,
        pre_lang_selector: Type[PreLanguageSelector] | None = None,
        post_lang_selector: Type[PostLanguageSelector] | None = None,
    ):
        """
        初始化I18n
        :param languages: 要启用的语言
        :param global_lang: 全局默认使用的语言
        :param sep: 字符串分隔符
        :param i18n_function_names: 翻译函数名
        :param pre_lang_selector: 前置语言选择器类
        :param post_lang_selector: 后置语言选择器类
        """
        self._cache: dict[str, ast.Call] = {}
        self._parse_failures: set[str] = set()

        self.global_lang = global_lang
        self.languages = to_list(languages)
        if self.languages and self.global_lang not in self.languages:
            self.languages.append(self.global_lang)

        self.sep = sep or ic.def_sep
        self.i18n_file_dir = i18n_file_dir or ic.i18n_dir
        self.i18n_function_names = (
            to_list(i18n_function_names) or ic.i18n_function_names
        )
        self.pre_lang_selector = pre_lang_selector or PreLanguageSelector
        self.post_lang_selector = post_lang_selector or PostLanguageSelector
        self.content = I18nContent
        self.i18n_dict = Loader(self.i18n_file_dir).load_i18n_file(self.languages)

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
                post_lang_selector=self.post_lang_selector,
            )
        positions = (
            f.f_lineno,
            f.f_lasti,
        )
        cache_key = gen_id(positions)

        # 解析错误的内容直接返回原文
        if cache_key in self._parse_failures:
            return self.content(
                text=original,
                i18n_dict=self.i18n_dict,
                post_lang_selector=self.post_lang_selector,
            )

        # 获取缓存的节点
        call_node = self._cache.get(cache_key, None)

        try:
            result = ASTParser(
                sep=sep, i18n_function_names=self.i18n_function_names
            ).extract(frame=f, call_node=call_node)
            return self._handle_cache(original, cache_key, result)
        except Exception:
            logger.exception("I18N解析错误")
            self._parse_failures.add(cache_key)
            return self.content(
                text=original,
                i18n_dict=self.i18n_dict,
                post_lang_selector=self.post_lang_selector,
            )
        finally:
            # noinspection PyInconsistentReturns
            del f

    def _handle_cache(
        self, original: str, cache_key: str, result: StringData
    ) -> I18nContent:
        """处理缓存并返回结果"""
        if not result:
            self._parse_failures.add(cache_key)
            logger.exception(f"I18N解析错误: {original}")
            return self.content(
                text=original,
                i18n_dict=self.i18n_dict,
                post_lang_selector=self.post_lang_selector,
            )

        self._cache[cache_key] = result.call_node
        return self.content(
            text=result.string,
            i18n_dict=self.i18n_dict,
            variables=result.variables,
            lang=self.global_lang,
            post_lang_selector=self.post_lang_selector,
        )

    def clear_cache(self):
        """清除解析缓存"""
        self._cache.clear()
        self._parse_failures.clear()

    def __getitem__(self, lang: any) -> PreLanguageSelector:
        """调用前置语言选择器"""
        return self.pre_lang_selector(i18n=self, lang=lang, sep=self.sep)

    def __call__(self, *args, sep: str = None) -> I18nContent:
        """调用入口函数"""
        frame = inspect.currentframe().f_back
        return self.t(*args, sep=sep or self.sep, frame=frame)
