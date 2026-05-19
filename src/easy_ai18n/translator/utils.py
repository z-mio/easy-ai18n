from openai.types.chat import ChatCompletionMessageParam


def build_messages(prompt: str, content: str) -> list[ChatCompletionMessageParam]:
    return [
        {
            "role": "system",
            "content": prompt,
        },
        {
            "role": "user",
            "content": content,
        },
    ]
