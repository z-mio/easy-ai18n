"""
Translator ABCs and implementations.
"""

from __future__ import annotations

import abc
import asyncio
import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from . import TextId, TextMap
from .errors import BuildDependencyError, TranslationError

if TYPE_CHECKING:
    from pydantic_ai import Agent


__all__ = [
    "BaseTranslator",
    "GoogleTranslator",
    "LLMItemTranslator",
    "TranslatorResult",
    "LLMBulkTranslator",
]


# ── ABC ──────────────────────────────────────────────────────────


class BaseTranslator(abc.ABC):
    """Translator base: chunking, concurrency and progress live here.

    Subclasses only implement ``translate_chunk`` — how one chunk of
    texts is translated. The granularity is controlled by
    ``batch_size`` (``1`` = one API call per text, ``>1`` = one API
    call per chunk) and ``max_concurrency`` (how many chunks run in
    parallel).
    """

    def __init__(self, *, batch_size: int = 1, max_concurrency: int = 10) -> None:
        """Set up the translator.

        Args:
            batch_size: The number of texts translated per chunk.
                ``1`` means one API call per text, ``>1`` means one
                API call per chunk of this size.
            max_concurrency: The maximum number of chunks running
                concurrently.
        """
        self.batch_size = batch_size
        self.max_concurrency = max_concurrency

    @abc.abstractmethod
    async def translate_chunk(self, texts: TextMap, target_lang: str) -> TextMap:
        """Translate a single chunk of texts (``batch_size`` items)."""
        raise NotImplementedError()

    async def translate(
        self,
        texts: TextMap,
        target_lang: str,
        on_progress: Callable[[int], None] | None = None,
    ) -> TextMap:
        """Translate texts by slicing them into chunks.

        The default implementation slices ``texts`` into chunks of
        ``batch_size``, runs them concurrently under a semaphore of
        ``max_concurrency``, merges the results and reports progress
        per completed chunk.
        """
        items = list(texts.items())
        sem = asyncio.Semaphore(self.max_concurrency)

        async def run_chunk(chunk: TextMap) -> TextMap:
            async with sem:
                result = await self.translate_chunk(chunk, target_lang)
                if on_progress:
                    on_progress(len(chunk))
                return result

        chunks = [dict(items[i : i + self.batch_size]) for i in range(0, len(items), self.batch_size)]
        results = await asyncio.gather(*(run_chunk(c) for c in chunks))
        merged: TextMap = {}
        for r in results:
            merged |= r
        return merged


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
    """Google Translate translator (one API call per text)."""

    async def translate_chunk(self, texts: TextMap, target_lang: str) -> TextMap:
        from googletrans import Translator

        result: TextMap = {}
        for key, text in texts.items():
            last_exc: Exception | None = None
            for _ in range(3):
                try:
                    translated = await Translator().translate(text, dest=target_lang)
                except Exception as e:
                    last_exc = e
                    await asyncio.sleep(1.5)
                else:
                    result[TextId(key)] = str(translated.text)
                    break
            else:
                raise TranslationError(f"Google Translate error: {last_exc}") from last_exc
        return result


# ── OpenAI ──────────────────────────────────────────────────────


def _create_openai_agent[OutputT](
    output_type: type[OutputT],
    *,
    api_key: str | None,
    base_url: str | None,
    model: str,
    prompt: str,
) -> Agent[object, OutputT]:
    """Build an OpenAI-compatible pydantic-ai Agent with translation defaults."""
    try:
        from pydantic_ai import Agent
        from pydantic_ai.models.openai import OpenAIChatModel
        from pydantic_ai.providers.openai import OpenAIProvider
        from pydantic_ai.settings import ModelSettings
    except ImportError as e:
        raise BuildDependencyError() from e

    # 类型参数不能用于运行期表达式, 这里用 Any; 实际输出类型由 output_type 参数决定
    return Agent[object, Any](
        model=OpenAIChatModel(
            model,
            provider=OpenAIProvider(api_key=api_key, base_url=base_url),
        ),
        output_type=output_type,
        system_prompt=prompt,
        model_settings=ModelSettings(temperature=0, thinking=False),
        retries=3,
    )


class LLMItemTranslator(BaseTranslator):
    """LLM translator — one API call per text (with concurrency).

    Pass a custom ``agent`` to use any pydantic-ai model or provider;
    otherwise an OpenAI-compatible agent is built from the other args.
    """

    def __init__(
        self,
        agent: Agent[object, str] | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str = "gpt-5-mini",
        prompt: str = TRANSLATE_PROMPT,
        max_concurrency: int = 10,
    ) -> None:
        super().__init__(batch_size=1, max_concurrency=max_concurrency)
        self._agent = (
            agent
            if agent is not None
            else _create_openai_agent(str, api_key=api_key, base_url=base_url, model=model, prompt=prompt)
        )

    async def translate_chunk(self, texts: TextMap, target_lang: str) -> TextMap:
        result: TextMap = {}
        for key, text in texts.items():
            response = await self._agent.run(
                f"Translate the text to {target_lang}:\n{text}",
            )
            result[TextId(key)] = str(response.output)
        return result


@dataclass
class TranslatorResult:
    """A single translated item returned by a bulk LLM translator."""

    key: str
    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.key, str) or not re.fullmatch(r"[0-9a-fA-F]{12}", self.key):
            raise ValueError(f"Invalid key: {self.key!r}, expected 12 hex characters")


class LLMBulkTranslator(BaseTranslator):
    """LLM translator — multiple items per API call (batch).

    Pass a custom ``agent`` to use any pydantic-ai model or provider;
    otherwise an OpenAI-compatible agent is built from the other args.
    """

    def __init__(
        self,
        agent: Agent[object, Any] | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str = "gpt-5-mini",
        prompt: str = TRANSLATE_PROMPT,
        batch_size: int = 50,
    ) -> None:
        super().__init__(batch_size=batch_size, max_concurrency=1)
        self._agent = (
            agent
            if agent is not None
            else _create_openai_agent(
                list[TranslatorResult], api_key=api_key, base_url=base_url, model=model, prompt=prompt
            )
        )

    async def translate_chunk(self, texts: TextMap, target_lang: str) -> TextMap:
        try:
            text = json.dumps(texts, ensure_ascii=False)
            response = await self._agent.run(
                f"Translate the text to {target_lang}:\n{text}",
            )
        except Exception as e:
            raise TranslationError(f"OpenAI translation error: {e}") from e
        return {TextId(item.key): item.value for item in response.output}
