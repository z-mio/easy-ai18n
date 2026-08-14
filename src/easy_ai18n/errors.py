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
    def __init__(self, message: str | None = None) -> None:
        msg = message or "Missing dependencies. Install with: pip install easy_ai18n[build]"
        super().__init__(msg)
