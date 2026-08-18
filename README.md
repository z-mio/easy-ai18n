<div align="center">

<a href="https://github.com/z-mio/easy-ai18n">
    <img src="docs/image/logo.png" width="100" alt="icon">
</a>

**Simple and Elegant Python3 Internationalization (i18n) Library**

[![Python](https://img.shields.io/badge/python-3.12+-yellow)](https://www.python.org/)
[![GitHub stars](https://img.shields.io/github/stars/z-mio/easy-ai18n.svg?style=social&label=Stars)](https://github.com/z-mio/easy-ai18n)
[![GitHub forks](https://img.shields.io/github/forks/z-mio/easy-ai18n.svg?style=social&label=Forks)](https://github.com/z-mio/easy-ai18n)
[![PyPI version](https://badge.fury.io/py/easy-ai18n.svg)](https://badge.fury.io/py/easy-ai18n)
[![GitHub License](https://img.shields.io/github/license/z-mio/easy-ai18n)](https://github.com/z-mio/easy-ai18n/blob/master/LICENSE)

**English | [中文](README.zh.md) | [日本語](README.ja.md)**

</div>

# 🌍 Easy AI18n

Easy AI18n is a modern Python3 internationalization library that supports AI translation, multi-user scenarios, and the
complete string formatting syntax, making project globalization more elegant and natural.

## ✨ Key Features:

- **🚀 Simple and Easy:** Internationalize your project with just a few lines of code
- **✨ Elegant Syntax:** Blends naturally into your existing code
- **🤖 AI Translation:** Supports translation with large language models (LLM) for high-quality results
- **📝 Formatting Compatible:** Full support for all Python string formatting syntax
- **🌐 Dynamic Multi-language:** Supports dynamic language selection at runtime

## 🔍 Comparison with Other i18n Tools

|                                            Other i18n Tools                                             |                                                         EasyAI18n                                                         |
|:-------------------------------------------------------------------------------------------------------:|:-------------------------------------------------------------------------------------------------------------------------:|
| ![](docs/image/1.png)<br/>**Requires manually maintaining `key` and i18n files, high development cost** |           ![](docs/image/2.png)<br/>**Automatically extracts translatable content, no manual file maintenance**           |
|                ![](docs/image/3.png)<br/>**Only supports part of the formatting syntax**                |                           ![](docs/image/4.png)<br/>**Full support for all formatting syntax**                            |
|   ![](docs/image/5.png)<br/>**No runtime language switching, not suitable for multi-user scenarios**    | ![](docs/image/6.png)<br/>**Supports the default locale and multi-language switching, ideal for multi-user environments** |

---

## ⚡ Quick Start

### 📦 Installation

```shell
# Install runtime dependencies (without the extra dependencies needed to build locale files)
uv add easy-ai18n

# Add the translation builder dependency to dev dependencies
uv add --dev "easy-ai18n[builder]"

```

### 🧪 Simple Example

`/i18n.py`

```python
from easy_ai18n import EasyAI18n

i18n = EasyAI18n("en")

_ = i18n.i18n()

if __name__ == "__main__":
    i18n.build(to_locales=["ja"])
```

`/main.py`

```python
from i18n import _

print(_("Hello, world!")['ja'])
```

## 📘 Usage Guide

### 🔎 Language Selector

The language selector is the core mechanism Easy AI18n uses to retrieve multi-language results: a single translation
produces all languages at once, and you pick from them as needed. It works in two directions:

- **Pre locale selector** `_['ja']("text")`: locks the language first, then translates the text — suitable for scopes
  with a fixed language (e.g. all text within a user session)
- **Post locale selector** `_("text")['ja']` / `_("text")('ja')`: translates first to obtain a `LocaleContent`, then
  picks the language from it — suitable for retrieving different languages on a per-call basis

The result of translation is **LocaleContent** `_("text")`: it exists as a string in the default locale, carrying
translations for all languages internally, ready for on-demand retrieval later.

When no language is specified, the default locale text is returned (by default this is the source language
`source_locale`; the source language has no translation files, so the original text is returned directly; this can be
overridden with `default_locale`). The selector is not limited to language codes: a custom selector can accept any
object (e.g. Telegram's `Message`) and resolve the user's language from it, enabling dynamic switching in multi-user
scenarios.

All the forms and their types are as follows:

```python
_ = i18n.i18n()  # I18n: translation function

_t: PreLocaleSelector = _['ja']  # Pre locale selector: locks the language (a str language code when unspecified)
_t("text")  # Pre locale selector call
_['ja']("text")  # Equivalent form (without binding a variable)

content: LocaleContent = _("text")  # Multi-language object: a string in the default locale, containing all languages
content['ja']  # Post locale selector (index to get a language)
content('ja')  # Post locale selector (call to get a language, equivalent to indexing)
_("text")['ja']  # Equivalent form (without binding a variable)
```

Example:

```python
from easy_ai18n import EasyAI18n

i18n = EasyAI18n("en", func_names=['_', '_t'])
_ = i18n.i18n()
_t = _['ja']  # Pre locale selector: locks Japanese

d = {
    1: _('apple'),  # Default locale (source language en) -> original text
    2: _('banana'),
    3: _t('orange'),  # Pre locale selector -> Japanese
}
print(d[1]['zh-hans'])  # Post locale selector: get Simplified Chinese  output: 苹果
print(d[2])  # Default locale output            output: banana
print(d[3])  # Pre locale selector output          output: みかん
```

**Overriding the default locale**:

```python
_ = i18n.i18n(default_locale="ja")
print(_('apple'))  # Default locale is ja, outputs Japanese directly
```

### ⚙️ Build Options

`build()` supports controlling the extraction scope and concurrency behavior:

```python
i18n.build(
    to_locales=["ja", "ru"],
    project_root="./",
    # Scan root directory (defaults to the current working directory; include/exclude are resolved relative to it)
    include=["src/**"],  # Only extract matching files/directories (glob supported)
    exclude=["tests/**", "build/**"],  # Exclude files or directories (.venv/.git/.idea excluded by default)
    concurrent_locales=False,
    # Translate locales concurrently (default True; recommended to disable for free/rate-limited APIs)
    max_retries=3,  # Extra retry attempts after a single locale fails (default 2)
)
```

**Custom locale directory**: generated in `./i18n` by default; change it via `locales_dir`:

```python
i18n = EasyAI18n("en", locales_dir="./locales")
```

### 📝 String Formatting and Variable Interpolation

Full support for f-string variable interpolation and all Python formatting syntax

```python
from easy_ai18n import EasyAI18n

i18n = EasyAI18n("en")
_ = i18n.i18n()

name = "Alice"
count = 3

print(_(f"Hello, {name}!")['zh-hans'])  # output: 你好, Alice!
print(_(f"Count: {count:02d}")['zh-hans'])  # output: 数量: 03
print(_(f"Value: {count!r}")['zh-hans'])  # output: 值: 3

# Multiple arguments are joined automatically (separated by a space by default)
print(_("Hello", "world")['zh-hans'])  # output: 你好 世界

# sep= custom separator (can also be set globally at construction: EasyAI18n("en", sep="-"))
print(_("Hello", "world", sep="-")['zh-hans'])  # output: 你好-世界
```

### 🛠️ Custom Translation Function Names

```python
from easy_ai18n import EasyAI18n

i18n = EasyAI18n(
    "en",
    func_names=["_t", "_"]  # Custom translation function names
)

_t = i18n.i18n()
_ = _t

print(_t("Hello, world!"))
print(_("Hello, world!"))
```

### 🤖 Translating with AI

**Default translator**: when `translator` is not passed, `build()` uses the free `GoogleTranslator` by default, no
configuration required:

```python
i18n.build(to_locales=["ja"])  # Default GoogleTranslator
```

**Two LLM translation modes**:

- Bulk `LLMBulkTranslator` translates multiple texts at once
- Per-item `LLMItemTranslator` translates one text at a time

```python
from easy_ai18n import EasyAI18n
from easy_ai18n.translators import LLMBulkTranslator

translator = LLMBulkTranslator(api_key="...", base_url="...", model="gpt-5-mini")

i18n = EasyAI18n("en")
i18n.build(to_locales=["ru", "ja", "zh-hant"], translator=translator)

_ = i18n.i18n()

print(_("Hello, world!")['zh-hant'])
```

**Custom Agent**: both LLM translators support passing any pydantic-ai Agent, so you can connect local models or other
providers:

```python
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider
from easy_ai18n.translators import LLMItemTranslator

agent = Agent(
    model=OpenAIChatModel(
        "qwen2.5:7b",  # Local Ollama model
        provider=OpenAIProvider(api_key="ollama", base_url="http://localhost:11434/v1"),
    ),
    output_type=str,  # Change to list[TranslatorResult] when using LLMBulkTranslator
)

translator = LLMItemTranslator(agent=agent)
```

### 🛠️ Custom Translators

Just subclass `BaseTranslator` and implement `translate_chunk`:

```python
from easy_ai18n import EasyAI18n, TextMap
from easy_ai18n.translators import BaseTranslator


class MyTranslator(BaseTranslator):
    async def translate_chunk(self, *, texts: TextMap, target_lang: str, source_lang: str) -> TextMap:
        # Implement the translation logic
        ...


i18n = EasyAI18n("zh-hans")
i18n.build(
    to_locales=["ja"],
    translator=MyTranslator(),
)
```

### 👥 Multi-user Language Scenarios (e.g. Telegram Bot)

Implement dynamic language selection in multi-user environments via a custom language selector:

`/i18n.py`:

```python
from pyrogram.types import Message
from easy_ai18n import EasyAI18n, PostLocaleSelector


class MyPostLocaleSelector(PostLocaleSelector[Message]):
    def __getitem__(self, locale: Message | str) -> str:
        if isinstance(locale, str):
            return super().__getitem__(locale)
        return super().__getitem__(locale.from_user.language_code)


i18n = EasyAI18n("en")

t_ = i18n.i18n(post_locale_selector=MyPostLocaleSelector)

if __name__ == "__main__":
    i18n.build(to_locales=["en", "ru"])
```

`/bot.py`:

```python
from pyrogram import Client
from pyrogram.types import Message
from i18n import t_

bot = Client("my_bot")


@bot.on_message()
async def start(_, msg: Message):
    await msg.reply(t_[msg]("Hello, world!"))


if __name__ == "__main__":
    bot.run()
```

## 📂 Example Projects

**Real-world projects using Easy AI18n**

- **[z-mio/parse_hub_bot](https://github.com/z-mio/parse_hub_bot)**

## 🗂️ Project Structure

```text
easy_ai18n
├── __init__.py          # EasyAI18n entry + public API
├── i18n.py              # Translation runtime (I18n, Pre/PostLocaleSelector, LocaleContent)
├── translators.py       # Translators (ABC + GoogleTranslator + LLM*Translator)
├── errors.py            # Exception classes
├── py.typed             # PEP 561 type marker
├── _builder.py          # Builder: extract, translate, generate YAML files
├── _parser.py           # AST parser
├── _progress.py         # Progress display (rich progress bar / falls back to line reports outside a terminal)
├── _loader.py           # Loader: load locale files
└── _types.py            # Text/TextId/TextMap type definitions
```

## 📜 License

This project is open-sourced under the [MIT License](LICENSE)

---

<div align="center">

**If this project helps you, feel free to give it a ⭐ Star!**

</div>
