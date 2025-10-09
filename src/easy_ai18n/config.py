import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


class I18nConfig:
    func_names: list[str] = ["_"]
    """翻译函数的名称"""

    locales_dir = os.getcwd() / Path("i18n")
    """语言文件存放目录"""

    sep = " "
    """默认分隔符"""


ic = I18nConfig()
