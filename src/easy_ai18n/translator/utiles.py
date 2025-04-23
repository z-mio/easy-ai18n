def build_messages(prompt, content) -> list:
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
