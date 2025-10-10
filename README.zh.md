<div align="center">

<a href="https://github.com/z-mio/easy-ai18n">
    <img src="docs/image/logo.png" width="100" alt="icon">
</a>

**简单、优雅的 Python3 国际化(i18n)工具**

[![Python](https://img.shields.io/badge/python-3.12+-yellow)](https://www.python.org/)
[![GitHub stars](https://img.shields.io/github/stars/z-mio/easy-ai18n.svg?style=social&label=Stars)](https://github.com/z-mio/easy-ai18n)
[![GitHub forks](https://img.shields.io/github/forks/z-mio/easy-ai18n.svg?style=social&label=Forks)](https://github.com/z-mio/easy-ai18n)
[![PyPI version](https://badge.fury.io/py/easy-ai18n.svg)](https://badge.fury.io/py/easy-ai18n)
[![GitHub License](https://img.shields.io/github/license/z-mio/easy-ai18n)](https://github.com/z-mio/easy-ai18n/blob/master/LICENSE)

[English](https://github.com/z-mio/easy-ai18n) | 中文 | [日本語](README.ja.md)

</div>

# 🌍 Easy AI18n

Easy AI18n 是一款现代化的 Python3 国际化工具库，支持 AI 翻译、多用户场景以及完整的字符串格式化语法，让项目全球化变得更加优雅自然。

## ✨ 主要特性:

- **🚀 简单易用:** 几行代码即可轻松实现国际化
- **✨ 语法优雅:** 通过 `_()` 包裹待翻译文本，自然融入原有代码
- **🤖 AI 翻译:** 支持使用大语言模型（LLM）进行翻译，确保高质量结果
- **📝 格式化兼容:** 完整支持所有 Python 字符串格式化语法
- **🌐 多语言支持:** 通过 `[]` 语言选择器, 支持多语言选择

## 🔍 对比其他 i18n 工具

|                        其他 i18n 工具                         |                     EasyAI18n                      |
|:---------------------------------------------------------:|:--------------------------------------------------:|
| ![](docs/image/1.png)<br/>**需手动维护 `key` 与 i18n 文件，开发成本高** |  ![](docs/image/2.png)<br/>**自动提取翻译内容，无需手动维护文件**   |
|         ![](docs/image/3.png)<br/>**仅支持部分格式化语法**          |     ![](docs/image/4.png)<br/>**完全支持所有格式化语法**      |
|    ![](docs/image/5.png)<br/>**不支持实时多语言切换，不适用于多用户场景**     | ![](docs/image/6.png)<br/>**支持默认语言与多语言切换，适配多用户环境** |

---

## ⚡ 快速开始

### 📦 安装

```shell
pip install easy-ai18n
```

### 🧪 简单示例

`/i18n.py`

```python
from easy_ai18n import EasyAI18n

i18n = EasyAI18n()

_ = i18n.i18n()

if __name__ == "__main__":
    i18n.build(to_locales=["ja"])
```

`/main.py`

```python
from i18n import _


def main():
    print(_("Hello, world!")['ja'])


if __name__ == "__main__":
    main()
```

## 🗂️ 项目结构

```text
easy_ai18n
├── core                 # 核心功能模块
│   ├── builder.py       # 构建器：提取、翻译、生成 YAML 文件
│   ├── i18n.py          # 翻译主逻辑
│   ├── loader.py        # 加载器：加载翻译文件
│   └── parser.py        # AST 语法树解析器
├── prompts              # 翻译提示词
├── translator           # 翻译器模块
└── main.py              # 项目入口封装

```

## 📘 使用教程

### 🛠️ 自定义翻译函数名称

```python
from easy_ai18n import EasyAI18n

i18n = EasyAI18n(
    func_names=["_t", '_']  # 自定义翻译函数名称
)

_t = i18n.i18n()
_ = _t

print(_t("Hello, world!"))
print(_("Hello, world!"))
```

### 🤖 使用 AI 进行翻译

```python
from easy_ai18n import EasyAI18n
from easy_ai18n.translator import OpenAIBulkTranslator

translator = OpenAIBulkTranslator(api_key=..., base_url=..., model='gpt-4o-mini')

i18n = EasyAI18n()
i18n.build(to_locales=["ru", "ja", 'zh-Hant'], translator=translator)

_ = i18n.i18n()

print(_("Hello, world!")['zh-Hant'])
```

### 🔎 语言选择器

```python
from easy_ai18n import EasyAI18n

i18n = EasyAI18n()
_ = i18n.i18n()
_t = _['ja']

d = {
    1: _('apple'),
    2: _('banana'),
    3: _t('orange'),
}
print(d[1]['zh-hans'])  # output: 苹果
print(d[2])  # output: banana
print(d[3])  # output: みかん
```

### 👥 多用户语言场景（如 Telegram Bot）

通过自定义语言选择器, 在多用户环境中实现动态语言选择:

`/i18n.py`:

```python
from pyrogram.types import Message
from easy_ai18n import EasyAI18n, PostLocaleSelector


class MyPostLocaleSelector(PostLocaleSelector):
    def __getitem__(self, msg: Message):
        # ......
        lang = msg.from_user.language_code
        return super().__getitem__(lang)


i18n = EasyAI18n()

_ = i18n.i18n(post_locale_selector=MyPostLocaleSelector)

if __name__ == "__main__":
    i18n.build(to_locales=['en', 'ru'])
```

`/bot.py`:

```python
from pyrogram import Client
from pyrogram.types import Message
from i18n import _

bot = Client("my_bot")


@bot.on_message()
async def start(__, msg: Message):
    await msg.reply(_[msg]("Hello, world!"))


if __name__ == "__main__":
    bot.run()
```