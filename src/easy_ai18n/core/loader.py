from pathlib import Path

import yaml


class Loader:
    def __init__(self, locales_dir: str | Path):
        self.locales_dir = locales_dir

    def load_locale_file(self, locales: list[str] = None) -> dict[str, dict]:
        """
        加载 locales 目录下的 yaml 文件
        :return: locales 字典
        """
        locales_dict = {}
        locale_files = self.locales_dir.glob("**/*.yaml")
        if locales:
            locale_files = [file for file in locale_files if file.name.split(".")[0] in locales]

        if not locale_files:
            return {}

        for file in locale_files:
            f = yaml.safe_load(Path(file).read_text(encoding="utf-8"))
            if not f:
                continue
            locales_dict[file.name.split(".")[0]] = f

        return locales_dict
