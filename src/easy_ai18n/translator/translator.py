"""
翻译器
"""

import asyncio
from pprint import PrettyPrinter

from pydantic import BaseModel, Field

from ..errors import BuildDependencyError, TranslationError
from .base import BaseBulkTranslator, BaseItemTranslator

try:
    from googletrans import Translator as Gt
    from pydantic_ai import Agent
    from pydantic_ai.models.openai import OpenAIChatModel
    from pydantic_ai.providers.openai import OpenAIProvider
except ImportError as e:
    raise BuildDependencyError() from e

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


class GoogleTranslator(BaseItemTranslator):
    """谷歌翻译"""

    async def translate(self, text: str, target_lang: str) -> str:
        last_exc: Exception | None = None
        for _ in range(3):
            try:
                result = await Gt().translate(text, dest=target_lang)
            except Exception as e:
                last_exc = e
                await asyncio.sleep(1.5)
            else:
                return str(result.text)
        raise TranslationError(f"谷歌翻译错误: {last_exc}") from last_exc


class BaseOpenAITranslator:
    """OpenAI 翻译器基础配置"""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        prompt: str = TRANSLATE_PROMPT,
    ):
        self.api_key = api_key
        self.base_url = base_url
        self.model = model or "gpt-5-mini"
        self.prompt = prompt

    def _create_model(self) -> OpenAIChatModel:
        """创建 OpenAI Chat Model。"""
        return OpenAIChatModel(
            self.model,
            provider=OpenAIProvider(
                api_key=self.api_key,
                base_url=self.base_url,
            ),
        )


class OpenAIItemTranslator(BaseItemTranslator, BaseOpenAITranslator):
    """OpenAI翻译器 | 逐条翻译"""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        prompt: str = TRANSLATE_PROMPT,
    ):
        """
        :param api_key: OpenAI API Key
        :param base_url: OpenAI API URL
        :param model: 模型
        :param prompt: 提示词
        """
        BaseOpenAITranslator.__init__(self, api_key, base_url, model, prompt)
        self._agent = Agent[object, str](
            self._create_model(),
            system_prompt=self.prompt,
            model_settings={"temperature": 0, "thinking": False},
            retries=3,
        )

    async def translate(self, text: str, target_lang: str) -> str:
        """GPT 逐条翻译。"""

        result = await self._agent.run(
            f"Translate the text to {target_lang}:\n{text}",
        )
        return result.output


class TranslatorResult(BaseModel):
    key: str = Field(..., pattern=r"^[0-9a-fA-F]{12}$", strict=True, description="key")
    value: str = Field(..., description="value")


class OpenAIBulkTranslator(BaseBulkTranslator, BaseOpenAITranslator):
    """OpenAI翻译器 | 整体翻译"""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        prompt: str = TRANSLATE_PROMPT,
    ):
        """
        :param api_key: OpenAI API Key
        :param base_url: OpenAI API URL
        :param model: 模型
        :param prompt: 提示词
        """
        BaseOpenAITranslator.__init__(self, api_key, base_url, model, prompt)
        self._agent = Agent[object, list[TranslatorResult]](
            model=self._create_model(),
            output_type=list[TranslatorResult],
            system_prompt=self.prompt,
            model_settings={"temperature": 0, "thinking": False},
            retries=3,
        )

    async def translate(self, text_id_dict: dict, target_lang: str) -> dict:
        """
        :param text_id_dict: 文本id字典，格式 {"text_id": "text"}
        :param target_lang: 目标语言
        :return: 合并后的翻译结果字典
        """
        try:
            text = PrettyPrinter().pformat(text_id_dict)
            response = await self._agent.run(
                f"Translate the text to {target_lang}:\n{text}",
            )
        except Exception as e:
            raise TranslationError(f"OpenAI翻译错误: {e}") from e

        return {item.key: item.value for item in response.output}
