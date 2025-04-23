"""
翻译器
"""

import os
from typing import List

import instructor
import yaml
from googletrans import Translator as Gt
from instructor.exceptions import InstructorRetryException
from openai import AsyncOpenAI

from .base import BaseItemTranslator, BaseBulkTranslator
from .utiles import build_messages
from ..error import TranslationError
from ..prompts.translate import TRANSLATE_PROMPT
from tenacity import retry, stop_after_attempt, wait_fixed
from pydantic import BaseModel, Field


class GoogleTranslator(BaseItemTranslator):
    """谷歌翻译"""

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(1.5))
    async def translate(self, text: str, target_lang: str) -> str:
        try:
            result = await Gt().translate(text, dest=target_lang)
        except Exception as e:
            raise TranslationError(f"谷歌翻译错误: {e}")
        else:
            return result.text


class BaseOpenAITranslator:
    def __init__(
        self,
        api_key: str = None,
        base_url: str = None,
        model: str = "gpt-4o-mini",
        prompt: str = TRANSLATE_PROMPT,
    ):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY 未配置")
        self.base_url = base_url or os.getenv("OPENAI_BASE_URL")
        self.model = model
        self.prompt = prompt


class OpenAITranslator(BaseItemTranslator, BaseOpenAITranslator):
    """逐条翻译的OpenAI翻译器"""

    def __init__(
        self,
        api_key: str = None,
        base_url: str = None,
        model: str = "gpt-4o-mini",
        prompt: str = TRANSLATE_PROMPT,
    ):
        """
        :param api_key: OpenAI API Key
        :param base_url: OpenAI API URL
        :param model: 模型
        :param prompt: 提示词
        """
        BaseOpenAITranslator.__init__(self, api_key, base_url, model, prompt)
        self.client = AsyncOpenAI(api_key=self.api_key, base_url=self.base_url)

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(1.5))
    async def translate(self, text: str, target_lang: str) -> str:
        """
        gpt翻译
        """
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=build_messages(self.prompt, target_lang, text),
                temperature=0,
            )
        except Exception as e:
            raise TranslationError(f"OpenAI翻译错误: {e}")
        else:
            return response.choices[0].message.content


class TranslatorResult(BaseModel):
    key: str = Field(..., description="key")
    value: str = Field(..., description="value")


class OpenAIYAMLTranslator(BaseBulkTranslator, BaseOpenAITranslator):
    """整体翻译的OpenAI翻译器"""

    def __init__(
        self,
        api_key: str = None,
        base_url: str = None,
        model: str = "gpt-4o-mini",
        prompt: str = TRANSLATE_PROMPT,
        batch_size: int = 50,
    ):
        """
        :param api_key: OpenAI API Key
        :param base_url: OpenAI API URL
        :param model: 模型
        :param prompt: 提示词
        :param batch_size: 每次请求的最大文本数
        """
        BaseOpenAITranslator.__init__(self, api_key, base_url, model, prompt)
        self.batch_size = batch_size
        self.client = instructor.from_openai(
            AsyncOpenAI(api_key=api_key, base_url=base_url)
        )

    async def translate(self, text_id_dict: dict, target_lang: str) -> dict:
        """
        :param text_id_dict: 文本id字典, 格式 {"text_id": "text"}
        :param target_lang: 目标语言
        :return: 合并后的翻译结果字典
        """
        all_results = {}
        items = list(text_id_dict.items())
        for i in range(0, len(items), self.batch_size):
            batch = dict(items[i : i + self.batch_size])
            try:
                text = yaml.dump(
                    batch, allow_unicode=True, canonical=True
                )  # 使用canonical规范格式, 避免换行影响结果
                response = await self.client.chat.completions.create(
                    model=self.model,
                    messages=build_messages(self.prompt, target_lang, text),
                    response_model=List[TranslatorResult],
                    max_retries=3,
                    temperature=0,
                )
            except InstructorRetryException as e:
                raise TranslationError(
                    f"OpenAI翻译结果验证错误: {e.messages[-1]['content']}"
                )
            except Exception as e:
                raise TranslationError(f"OpenAI翻译错误: {e}")
            else:
                batch_results = {kv.key: kv.value for kv in response}
                all_results.update(batch_results)
        return all_results
