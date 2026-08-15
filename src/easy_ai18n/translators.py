"""
Translator ABCs and implementations.
"""

from __future__ import annotations

import abc
import asyncio
from collections.abc import Callable
from pprint import pformat

from . import TextId, TextMap
from .errors import BuildDependencyError, TranslationError

try:
    from pydantic import BaseModel, Field
except ImportError as e:
    raise BuildDependencyError() from e


__all__ = [
    "BaseTranslator",
    "GoogleTranslator",
    "OpenAIItemTranslator",
    "TranslatorResult",
    "OpenAIBulkTranslator",
]


# ── ABC ──────────────────────────────────────────────────────────


class BaseTranslator(abc.ABC):
    """Abstract translator with optional progress reporting."""

    def __init__(self, max_concurrency: int = 10) -> None:
        self.max_concurrency = max_concurrency

    @abc.abstractmethod
    async def _translate_one(self, text: str, target_lang: str) -> str:
        """Translate a single text string."""
        raise NotImplementedError()

    async def translate_batch(
        self,
        texts: TextMap,
        target_lang: str,
        on_progress: Callable[[int], None] | None = None,
    ) -> TextMap:
        """Translate multiple texts concurrently.

        The default implementation calls ``_translate_one`` for each
        item with a semaphore for concurrency control.  Bulk translators
        should override this to send a single API request.
        """
        sem = asyncio.Semaphore(self.max_concurrency)

        async def _do(key: str, text: str) -> tuple[TextId, str]:
            async with sem:
                result = await self._translate_one(text, target_lang)
                if on_progress:
                    on_progress(1)
                return TextId(key), result

        tasks = [_do(k, t) for k, t in texts.items()]
        return dict(await asyncio.gather(*tasks))


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


class GoogleTranslator(BaseTranslator):
    """Google Translate translator."""

    async def _translate_one(self, text: str, target_lang: str) -> str:
        from googletrans import Translator

        last_exc: Exception | None = None
        for _ in range(3):
            try:
                result = await Translator().translate(text, dest=target_lang)
            except Exception as e:
                last_exc = e
                await asyncio.sleep(1.5)
            else:
                return str(result.text)
        raise TranslationError(f"Google Translate error: {last_exc}") from last_exc


# ── OpenAI ──────────────────────────────────────────────────────


class OpenAIItemTranslator(BaseTranslator):
    """OpenAI translator — translates items one by one (with concurrency)."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str = "gpt-5-mini",
        prompt: str = TRANSLATE_PROMPT,
        max_concurrency: int = 10,
    ) -> None:
        super().__init__(max_concurrency=max_concurrency)
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

    async def _translate_one(self, text: str, target_lang: str) -> str:
        result = await self._agent.run(
            f"Translate the text to {target_lang}:\n{text}",
        )
        return str(result.output)


class TranslatorResult(BaseModel):
    key: str = Field(..., pattern=r"^[0-9a-fA-F]{12}$", strict=True, description="key")
    value: str = Field(..., description="value")


class OpenAIBulkTranslator(BaseTranslator):
    """OpenAI translator — translates multiple items in one API call."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str = "gpt-5-mini",
        prompt: str = TRANSLATE_PROMPT,
        batch_size: int = 50,
    ) -> None:
        super().__init__(max_concurrency=1)
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
        self.batch_size = batch_size

    async def _translate_one(self, text: str, target_lang: str) -> str:
        raise NotImplementedError("OpenAIBulkTranslator does not support single-item translation")

    async def translate_batch(
        self,
        texts: TextMap,
        target_lang: str,
        on_progress: Callable[[int], None] | None = None,
    ) -> TextMap:
        items = list(texts.items())
        all_results: TextMap = {}
        for i in range(0, len(items), self.batch_size):
            batch = dict(items[i : i + self.batch_size])
            try:
                text = pformat(batch)
                response = await self._agent.run(
                    f"Translate the text to {target_lang}:\n{text}",
                )
            except Exception as e:
                raise TranslationError(f"OpenAI translation error: {e}") from e

            batch_results = {TextId(item.key): item.value for item in response.output}
            all_results |= batch_results
            if on_progress:
                on_progress(len(batch_results))
        return all_results
