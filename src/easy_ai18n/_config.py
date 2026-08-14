import os
from pathlib import Path


class I18nConfig:
    func_names: list[str] = ["_"]
    """Names of translation functions to recognize."""

    locales_dir: Path = Path(os.getcwd()) / "i18n"
    """Directory for YAML translation files."""

    sep: str = " "
    """Default separator between text parts."""


i18n_config = I18nConfig()
