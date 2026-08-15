"""
Translator ABCs and implementations.
"""

from __future__ import annotations

import abc
import asyncio
from pprint import PrettyPrinter

from .errors import BuildDependencyError, TranslationError

try:
    from pydantic import BaseModel, Field
except ImportError as e:
    raise BuildDependencyError() from e


__all__ = [
    "BaseItemTranslator",
    "BaseBulkTranslator",
    "GoogleTranslator",
    "OpenAIItemTranslator",
    "TranslatorResult",
    "OpenAIBulkTranslator",
]

# ── ABCs ────────────────────────────────────────────────────────


class BaseItemTranslator(abc.ABC):
    """Translator that processes one item at a time."""

    @abc.abstractmethod
    async def translate(self, text: str, target_lang: str) -> str:
        """Translate the given text to the target language."""
        raise NotImplementedError()


class BaseBulkTranslator(abc.ABC):
    """Translator that processes multiple items at once via LLM."""

    @abc.abstractmethod
    async def translate(self, text_id_dict: dict, target_lang: str) -> dict:
        """Translate multiple texts to the target language."""
        raise NotImplementedError()


# ── Shared constants ─────────────────────────────────────────────


DEFAULT_REFERENCE = (
    "You can adjust the tone and style, taking into account the cultural connotations "
    "and regional differences of certain words. As a translator, you need to translate "
    "the original text into a translation that meets the standards of accuracy and elegance."
)

TRANSLATE_PROMPT = f"""
Translate the text to the specified language
Here are some reference to help with better translation.  ---{DEFAULT_REFERENCE}---
Don't add anything extra, and don't modify python variables inside the text
"""


# ── Google Translate ────────────────────────────────────────────


class GoogleTranslator(BaseItemTranslator):
    """Google Translate translator."""

    async def translate(self, text: str, target_lang: str) -> str:
        from googletrans import Translator as GoogleTranslatorLib

        last_exc: Exception | None = None
        for _ in range(3):
            try:
                result = await GoogleTranslatorLib().translate(text, dest=target_lang)
            except Exception as e:
                last_exc = e
                await asyncio.sleep(1.5)
            else:
                return str(result.text)
        raise TranslationError(f"Google Translate error: {last_exc}") from last_exc


# ── OpenAI ──────────────────────────────────────────────────────


class OpenAIItemTranslator(BaseItemTranslator):
    """OpenAI translator — translates items one by one."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str = "gpt-5-mini",
        prompt: str = TRANSLATE_PROMPT,
    ):
        from pydantic_ai import Agent
        from pydantic_ai.models.openai import OpenAIChatModel
        from pydantic_ai.providers.openai import OpenAIProvider
        from pydantic_ai.settings import ModelSettings

        self._agent = Agent[object, str](
            model=OpenAIChatModel(
                model,
                provider=OpenAIProvider(api_key=api_key, base_url=base_url),
            ),
            system_prompt=prompt,
            model_settings=ModelSettings(temperature=0, thinking=False),
            retries=3,
        )

    async def translate(self, text: str, target_lang: str) -> str:
        result = await self._agent.run(
            f"Translate the text to {target_lang}:\n{text}",
        )
        return result.output


class TranslatorResult(BaseModel):
    key: str = Field(..., pattern=r"^[0-9a-fA-F]{12}$", strict=True, description="key")
    value: str = Field(..., description="value")


class OpenAIBulkTranslator(BaseBulkTranslator):
    """OpenAI translator — translates multiple items in bulk."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str = "gpt-5-mini",
        prompt: str = TRANSLATE_PROMPT,
    ):
        from pydantic_ai import Agent
        from pydantic_ai.models.openai import OpenAIChatModel
        from pydantic_ai.providers.openai import OpenAIProvider
        from pydantic_ai.settings import ModelSettings

        self._agent = Agent[object, list[TranslatorResult]](
            model=OpenAIChatModel(
                model,
                provider=OpenAIProvider(api_key=api_key, base_url=base_url),
            ),
            output_type=list[TranslatorResult],
            system_prompt=prompt,
            model_settings=ModelSettings(temperature=0, thinking=False),
            retries=3,
        )

    async def translate(self, text_id_dict: dict, target_lang: str) -> dict:
        try:
            text = PrettyPrinter().pformat(text_id_dict)
            response = await self._agent.run(
                f"Translate the text to {target_lang}:\n{text}",
            )
        except Exception as e:
            raise TranslationError(f"OpenAI translation error: {e}") from e

        return {item.key: item.value for item in response.output}
