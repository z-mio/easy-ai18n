class TranslationError(Exception):
    pass


class BuildedError(Exception):
    pass


class FormatError(Exception):
    pass


class EvaluateError(Exception):
    pass


class UnsupportedSyntaxError(Exception):
    pass


class BuildDependencyError(ImportError):
    def __init__(self) -> None:
        super().__init__("缺少依赖, 请安装 pip install easy_ai18n[build]")
