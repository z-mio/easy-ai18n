from pathlib import Path

import yaml

from ..config import ic


class Loader:
    @staticmethod
    def load_i18n_file(lang: str | list[str] = None) -> dict:
        """
        加载i18n目录下的yaml文件
        :return: i18n字典
        """
        if lang is not None:
            lang = lang if isinstance(lang, list) else [lang]

        i18n_dict = {}
        i18n_files = ic.i18n_dir.glob("**/*.yaml")
        if lang:
            lang = lang if isinstance(lang, list) else [lang]
            i18n_files = [
                file for file in i18n_files if file.name.split(".")[0] in lang
            ]

        if not i18n_files:
            return {}

        for file in i18n_files:
            yaml.safe_load(Path(file).read_text(encoding="utf-8"))
            i18n_dict[file.name.split(".")[0]] = yaml.safe_load(
                file.read_text(encoding="utf-8")
            )
        return i18n_dict



