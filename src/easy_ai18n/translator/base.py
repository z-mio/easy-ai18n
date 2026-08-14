import abc


class BaseItemTranslator(abc.ABC):
    """Translator that processes one item at a time."""

    @abc.abstractmethod
    async def translate(self, text: str, target_lang: str) -> str:
        """Translate the given text to the target language.

        Args:
            text: The text to translate.
            target_lang: The target language code.

        Returns:
            The translated text.
        """
        raise NotImplementedError()


class BaseBulkTranslator(abc.ABC):
    """Translator that processes multiple items at once via LLM."""

    @abc.abstractmethod
    async def translate(self, text_id_dict: dict, target_lang: str) -> dict:
        """Translate multiple texts to the target language.

        Args:
            text_id_dict: A dictionary of text IDs to texts,
                e.g. ``{"text_id": "text"}``.
            target_lang: The target language code.

        Returns:
            A dictionary of translated texts keyed by ID,
            e.g. ``{"text_id": "text"}``.
        """
        raise NotImplementedError()
