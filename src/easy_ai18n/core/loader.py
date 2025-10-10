from pathlib import Path

import yaml


class Loader:
    def __init__(self, locales_dir: str | Path):
        self.locales_dir = locales_dir

    def load_locales_file(self, locales: list[str] = None) -> dict[str, dict]:
        """
        加载 locales 目录下的 yaml 文件
        :return: locales 字典
        """
        locales_dict = {}
        yaml_files = self.locales_dir.glob("**/*.yaml")
        if locales:
            yaml_files = [file for file in yaml_files if file.name.split(".")[0] in locales]

        if not yaml_files:
            return {}

        for file in yaml_files:
            translation_data = yaml.safe_load(Path(file).read_text(encoding="utf-8"))
            if not translation_data:
                continue

            locale_code = file.name.split(".")[0]
            locales_dict[locale_code] = translation_data

        return locales_dict
