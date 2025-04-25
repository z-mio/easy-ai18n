from pathlib import Path

import yaml


class Loader:
    def __init__(self, i18n_file_dir: str | Path):
        self.i18n_file_dir = i18n_file_dir

    def load_i18n_file(self, lang: str | list[str] = None) -> dict:
        """
        加载i18n目录下的yaml文件
        :return: i18n字典
        """
        if lang is not None:
            lang = lang if isinstance(lang, list) else [lang]

        i18n_dict = {}
        i18n_files = self.i18n_file_dir.glob("**/*.yaml")
        if lang:
            lang = lang if isinstance(lang, list) else [lang]
            i18n_files = [
                file for file in i18n_files if file.name.split(".")[0] in lang
            ]

        if not i18n_files:
            return {}

        for file in i18n_files:
            f = yaml.safe_load(Path(file).read_text(encoding="utf-8"))
            if not f:
                continue
            i18n_dict[file.name.split(".")[0]] = f
        return i18n_dict
