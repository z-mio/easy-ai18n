<div align="center">

<img src="docs/image/logo.png" width="100" >

**Simple and Elegant Python3 Internationalization (i18n) Tool**

[![PyPI version](https://badge.fury.io/py/easy-ai18n.svg)](https://badge.fury.io/py/easy-ai18n)

English | [中文](docs/README.zh.md) | [日本語](docs/README.ja.md)

</div>

# 🌍 Easy AI18n

Easy AI18n is a modern internationalization tool library for Python3. It supports AI translation, multi-user scenarios, and full string formatting syntax,
making globalization of your project more elegant and natural.

## ✨ Key Features:

- **🚀 Easy to Use:** Implement i18n with just a few lines of code
- **✨ Elegant Syntax:** Use `_()` to wrap translatable texts, seamlessly integrating into your code
- **🤖 AI Translation:** Supports translation using large language models (LLMs) for high-quality results
- **📝 Full Formatting Support:** Fully supports all Python string formatting syntaxes
- **🌐 Multi-language Support:** Choose languages using `[]` selector for multilingual support

## 🔍 Comparison with Other i18n Tools

|                                             Other i18n Tools                                             |                                                         EasyAI18n                                                          |
|:--------------------------------------------------------------------------------------------------------:|:--------------------------------------------------------------------------------------------------------------------------:|
| ![](docs/image/1.png)<br/>**Requires manual maintenance of keys and i18n files, high development cost**  |        ![](docs/image/2.png)<br/>**Automatically extracts translation content, no manual file maintenance needed**         |
|                  ![](docs/image/3.png)<br/>**Supports only partial formatting syntax**                   |                             ![](docs/image/4.png)<br/>**Fully supports all formatting syntax**                             |
| ![](docs/image/5.png)<br/>**No real-time multi-language switching, unsuitable for multi-user scenarios** | ![](docs/image/6.png)<br/>**Supports default language and multi-language switching, adaptable to multi-user environments** |

---

## ⚡ Quick Start

### 📦 Installation

```shell
pip install easy-ai18n
```

### 🧪 Simple Example

```python
from easy_ai18n import EasyAI18n

i18n = EasyAI18n(target_lang=["ru", "ja", 'zh-CN'])
i18n.build()

_ = i18n.t()

print(_("Hello, world!")['zh-CN'])
```

## 🗂️ Project Structure

```
easy_ai18n
├── core                 # Core functionality module
│   ├── builder.py       # Builder: extract, translate, generate YAML files
│   ├── i18n.py          # Main translation logic
│   ├── loader.py        # Loader: load translation files
│   └── parser.py        # AST parser
├── prompts              # Translation prompts
├── translator           # Translator module
└── main.py              # Project entry point
```

## 📘 Usage Tutorial

### ⚙️ Initialize `EasyAI18n` Instance

```python
from easy_ai18n import EasyAI18n, PreLanguageSelector, PostLanguageSelector
from easy_ai18n.translator import GoogleTranslator

# Initialize EasyAI18n instance
i18n = EasyAI18n(
    global_lang="zh",  # Global default language
    target_lang=["zh", "ja"],  # Target translation languages
    languages=["zh", "ja"],  # Enabled languages (default is target_lang)
    project_dir="/path/to/your/project",  # Root directory (default is current dir)
    include=[],  # Included files/directories
    exclude=[".idea"],  # Excluded files/directories
    i18n_file_dir="i18n",  # Directory to store translation files
    func_name=["_"],  # Translation function names (supports multiple)
    sep=" ",  # Separator (default is space)
    translator=GoogleTranslator(),  # Translator (default is Google)
    pre_lang_selector=PreLanguageSelector,  # Pre language selector
    post_lang_selector=PostLanguageSelector  # Post language selector
)

# Build translation files
i18n.build()

# Set translation function, here we use _, can be customized
_ = i18n.t()

# Put strings to be translated inside the function
print(_("Hello, world!"))
```

### 🛠️ Custom Translation Function Names

```python
from easy_ai18n import EasyAI18n

i18n = EasyAI18n(
    func_name=["_t", '_']  # Custom translation function names
)

_t = i18n.t()
_ = _t

print(_t("Hello, world!"))
print(_("Hello, world!"))
```

### 🤖 Use AI for Translation

```python
from easy_ai18n import EasyAI18n
from easy_ai18n.translator import OpenAIYAMLTranslator

translator = OpenAIYAMLTranslator(api_key=..., base_url=..., model='gpt-4o-mini')

i18n = EasyAI18n(target_lang=["ru", "ja", 'zh-CN'], translator=translator)
i18n.build()

_ = i18n.t()

print(_("Hello, world!")['zh-CN'])
```

### 👥 Multi-user Language Scenarios (e.g. Telegram Bot)

Use custom language selector to dynamically select languages in multi-user environments:

```python
from pyrogram import Client
from pyrogram.types import Message

from easy_ai18n import EasyAI18n, PostLanguageSelector


class MyPostLanguageSelector(PostLanguageSelector):
    def __getitem__(self, msg: Message):
        # Get user's language
        lang = msg.from_user.language_code
        return super().__getitem__(lang)


i18n = EasyAI18n(
    target_lang=['zh', 'ru'],
    post_lang_selector=MyPostLanguageSelector,
)
_ = i18n.t()

bot = Client("my_bot")


@bot.on_message()
async def start(__, msg: Message):
    await msg.reply(_[msg]("Hello, world!"))


if __name__ == "__main__":
    bot.loop.run_until_complete(i18n.build_async())
    bot.run()
```

