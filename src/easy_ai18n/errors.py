class EasyAI18nError(Exception):
    pass


class TranslationError(EasyAI18nError):
    pass


class BuildError(EasyAI18nError):
    pass


class FormatError(EasyAI18nError):
    pass


class EvaluationError(EasyAI18nError):
    pass


class UnsupportedSyntaxError(EasyAI18nError):
    pass


class BuildDependencyError(EasyAI18nError):
    def __init__(self) -> None:
        super().__init__("Missing dependencies. Install with: pip install easy_ai18n[build]")
