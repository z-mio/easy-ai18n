from pathlib import Path

import yaml
from loguru import logger

from ._types import TextMap


class Loader:
    def __init__(self, locales_dir: Path):
        self.locales_dir = locales_dir

    def load_locales_file(self, locales: list[str] | None = None) -> dict[str, TextMap]:
        """Load YAML translation files from the locales directory.

        Args:
            locales: An optional list of language codes to load.
                If ``None``, all ``*.yaml`` files are loaded; an empty
                list loads nothing.

        Returns:
            A dictionary mapping locale codes to their translation
            dictionaries.
        """
        wanted = {code.lower() for code in locales} if locales is not None else None

        result: dict[str, TextMap] = {}
        for file in sorted(self.locales_dir.rglob("*.yaml")):
            locale_code = file.stem
            if wanted is not None and locale_code.lower() not in wanted:
                continue
            if locale_code in result:
                logger.warning(f"Duplicate locale file {file} ignored: {locale_code} already loaded")
                continue

            try:
                with file.open(encoding="utf-8") as f:
                    data = yaml.load(f, Loader=getattr(yaml, "CSafeLoader", yaml.SafeLoader))
            except (yaml.YAMLError, UnicodeDecodeError) as exc:
                raise ValueError(f"Failed to parse locale file {file}: {exc}") from exc

            if data is None:
                continue
            if not isinstance(data, dict):
                raise ValueError(f"Expected a mapping in {file}, got {type(data).__name__}")
            if data:
                result[locale_code] = data

        return result
