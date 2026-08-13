import os
from pathlib import Path


class I18nConfig:
    func_names: list[str] = ["_"]
    """翻译函数的名称"""

    locales_dir: Path = Path(os.getcwd()) / "i18n"
    """语言文件存放目录"""

    sep = " "
    """默认分隔符"""


ic = I18nConfig()
