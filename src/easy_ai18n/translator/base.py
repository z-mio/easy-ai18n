import abc


class BaseItemTranslator(abc.ABC):
    """普通翻译器"""

    @abc.abstractmethod
    async def translate(self, text: str, target_lang: str) -> str:
        """
        翻译
        :param text: 要翻译的文本
        :param target_lang: 目标语言
        :return:
        """
        raise NotImplementedError()


class BaseBulkTranslator(abc.ABC):
    """LLM翻译器"""

    @abc.abstractmethod
    async def translate(self, text_id_dict: dict, target_lang: str) -> dict:
        """
        翻译
        :param text_id_dict: 文本id字典, 格式 {"text_id": "text"}
        :param target_lang: 目标语言
        :return:
        """
        raise NotImplementedError()
