from pathlib import Path

import yaml


class Loader:
    def __init__(self, locales_dir: str | Path):
        self.locales_dir = Path(locales_dir)

    def load_locales_file(self, locales: list[str] | None = None) -> dict[str, dict]:
        """Load YAML translation files from the locales directory.

        Args:
            locales: An optional list of language codes to load.
                If ``None``, all YAML files are loaded.

        Returns:
            A dictionary mapping locale codes to their translation
            dictionaries.
        """
        locales_dict: dict[str, dict] = {}
        yaml_files = list(self.locales_dir.glob("**/*.yaml"))
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
