def build_messages(prompt, target_lang, text) -> list:
    return [
        {
            "role": "system",
            "content": prompt,
        },
        {
            "role": "user",
            "content": f"Translate the text to {target_lang}:\n{text}",
        },
    ]
