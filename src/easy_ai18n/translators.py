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

from loguru import logger

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
    async def translate_chunk(self, *, texts: TextMap, target_lang: str, source_lang: str) -> TextMap:
        """Translate a single chunk of texts (``batch_size`` items).

        Args:
            texts: The chunk of texts to translate.
            target_lang: The target language code.
            source_lang: The language code of the source texts
        """
        raise NotImplementedError()

    async def translate(
        self,
        *,
        texts: TextMap,
        target_lang: str,
        source_lang: str,
        on_progress: Callable[[int], None] | None = None,
    ) -> TextMap:
        """Translate texts by slicing them into chunks.

        The default implementation slices ``texts`` into chunks of
        ``batch_size``, runs them concurrently under a semaphore of
        ``max_concurrency``, merges the results and reports progress
        per completed chunk.

        Args:
            texts: The texts to translate.
            target_lang: The target language code.
            source_lang: The language code of the source texts, passed
                through to every chunk.
            on_progress: Called with the chunk size after each chunk.
        """
        items = list(texts.items())
        sem = asyncio.Semaphore(self.max_concurrency)

        async def run_chunk(chunk: TextMap) -> TextMap:
            async with sem:
                result = await self.translate_chunk(texts=chunk, target_lang=target_lang, source_lang=source_lang)
                if on_progress:
                    on_progress(len(chunk))
                return result

        chunks = [dict(items[i : i + self.batch_size]) for i in range(0, len(items), self.batch_size)]
        results = await asyncio.gather(*(run_chunk(c) for c in chunks))
        merged: TextMap = {}
        for r in results:
            merged |= r
        return merged


# ── Google Translate ────────────────────────────────────────────

# googletrans's table lacks the common zh-hans/zh-hant spellings; map
# them to the codes it does know.
_GOOGLE_ALIASES = {
    "zh-hans": "zh-cn",
    "zh-hant": "zh-tw",
}


def _lookup_google_code(code: str) -> str | None:
    """Resolve a language code the way googletrans validates it, or ``None``.

    Mirrors googletrans's own normalization — lowercase, strip a ``_xx``
    suffix, then ``LANGUAGES`` / ``SPECIAL_CASES`` / ``LANGCODES`` — and
    additionally applies :data:`_GOOGLE_ALIASES`.
    """
    from googletrans.constants import LANGCODES, LANGUAGES, SPECIAL_CASES

    resolved = code.lower().split("_", 1)[0]
    if resolved in LANGUAGES:
        return resolved
    if resolved in SPECIAL_CASES:
        return str(SPECIAL_CASES[resolved])
    if resolved in LANGCODES:
        return str(LANGCODES[resolved])
    if resolved in _GOOGLE_ALIASES:
        return _GOOGLE_ALIASES[resolved]
    return None


class GoogleTranslator(BaseTranslator):
    """Google Translate translator (one API call per text)."""

    def __init__(self) -> None:
        super().__init__()
        self._warned_unrecognized_src = False

    def _resolve_src(self, source_lang: str) -> str | None:
        """Return the googletrans source code, or ``None`` for auto-detection.

        googletrans validates ``src`` against its language table and
        raises ``ValueError`` for anything unknown, so a source code it
        does not recognize must fall back to automatic detection
        instead of failing every call.
        """
        resolved = _lookup_google_code(source_lang)
        if resolved is not None:
            return resolved
        if not self._warned_unrecognized_src:
            self._warned_unrecognized_src = True
            logger.warning(
                f"source_lang {source_lang!r} is not recognized by googletrans; "
                "falling back to automatic language detection"
            )
        return None

    def _resolve_dest(self, target_lang: str) -> str:
        """Return the googletrans destination code, failing fast when unknown.

        googletrans raises ``ValueError`` per call for unknown
        destinations, which would surface as a slow retry loop; checking
        up front turns it into one clear failure instead.
        """
        resolved = _lookup_google_code(target_lang)
        if resolved is not None:
            return resolved
        raise TranslationError(
            f"target_lang {target_lang!r} is not recognized by googletrans; "
            "use one of its language codes (e.g. en, ja, zh-cn, zh-tw)"
        )

    async def translate_chunk(self, *, texts: TextMap, target_lang: str, source_lang: str) -> TextMap:
        from googletrans import Translator

        src = self._resolve_src(source_lang) or "auto"
        dest = self._resolve_dest(target_lang)
        result: TextMap = {}
        for key, text in texts.items():
            last_exc: Exception | None = None
            for _ in range(3):
                try:
                    translated = await Translator().translate(text, dest=dest, src=src)
                except Exception as e:
                    last_exc = e
                    await asyncio.sleep(1.5)
                else:
                    result[TextId(key)] = str(translated.text)
                    break
            else:
                raise TranslationError(f"Google Translate error: {last_exc}") from last_exc
        return result


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


def _translation_prompt(target_lang: str, source_lang: str) -> str:
    """Build the per-call instruction, naming the source language."""
    return f"Translate the following {source_lang} text to {target_lang}:\n"


# ── LLM ──────────────────────────────────────────────────────


def _create_agent[OutputT](
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

    return Agent[object, Any](
        model=OpenAIChatModel(
            model,
            provider=OpenAIProvider(api_key=api_key, base_url=base_url),
        ),
        output_type=output_type,
        system_prompt=prompt,
        model_settings=ModelSettings(temperature=0),
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
            else _create_agent(str, api_key=api_key, base_url=base_url, model=model, prompt=prompt)
        )

    async def translate_chunk(self, *, texts: TextMap, target_lang: str, source_lang: str) -> TextMap:
        result: TextMap = {}
        prompt = _translation_prompt(target_lang, source_lang)
        for key, text in texts.items():
            response = await self._agent.run(f"{prompt}{text}")
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
            else _create_agent(list[TranslatorResult], api_key=api_key, base_url=base_url, model=model, prompt=prompt)
        )

    async def translate_chunk(self, *, texts: TextMap, target_lang: str, source_lang: str) -> TextMap:
        try:
            text = json.dumps(texts, ensure_ascii=False)
            prompt = _translation_prompt(target_lang, source_lang)
            response = await self._agent.run(f"{prompt}{text}")
        except Exception as e:
            raise TranslationError(f"LLM translation error: {e}") from e
        return {TextId(item.key): item.value for item in response.output}
