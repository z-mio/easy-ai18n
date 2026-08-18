<div align="center">

<a href="https://github.com/z-mio/easy-ai18n">
    <img src="docs/image/logo.png" width="100" alt="icon">
</a>

**简单, 优雅的 Python3 国际化 (i18n) 库**

[![Python](https://img.shields.io/badge/python-3.12+-yellow)](https://www.python.org/)
[![GitHub stars](https://img.shields.io/github/stars/z-mio/easy-ai18n.svg?style=social&label=Stars)](https://github.com/z-mio/easy-ai18n)
[![GitHub forks](https://img.shields.io/github/forks/z-mio/easy-ai18n.svg?style=social&label=Forks)](https://github.com/z-mio/easy-ai18n)
[![PyPI version](https://badge.fury.io/py/easy-ai18n.svg)](https://badge.fury.io/py/easy-ai18n)
[![GitHub License](https://img.shields.io/github/license/z-mio/easy-ai18n)](https://github.com/z-mio/easy-ai18n/blob/master/LICENSE)

**[English](https://github.com/z-mio/easy-ai18n) | 中文 | [日本語](README.ja.md)**

</div>

# 🌍 Easy AI18n

Easy AI18n 是一个现代化的 Python3 i18n 库, 支持 AI 翻译, 多用户场景以及完整的字符串格式化语法, 让项目全球化变得更加优雅自然

## ✨ 主要特性:

- **🚀 简单易用:** 几行代码即可轻松实现项目国际化
- **✨ 语法优雅:** 自然融入原有代码
- **🤖 AI 翻译:** 支持使用大语言模型 (LLM)进行翻译, 确保高质量结果
- **📝 格式化兼容:** 完整支持所有 Python 字符串格式化语法
- **🌐 动态多语言:** 支持运行时动态选择语言

## 🔍 对比其他 i18n 工具

|                              其他 i18n 工具                              |                               EasyAI18n                                |
|:------------------------------------------------------------------------:|:----------------------------------------------------------------------:|
| ![](docs/image/1.png)<br/>**需手动维护 `key` 与 i18n 文件, 开发成本高**  |    ![](docs/image/2.png)<br/>**自动提取翻译内容, 无需手动维护文件**    |
|            ![](docs/image/3.png)<br/>**仅支持部分格式化语法**            |          ![](docs/image/4.png)<br/>**完全支持所有格式化语法**          |
| ![](docs/image/5.png)<br/>**不支持运行时多语言切换, 不适用于多用户场景** | ![](docs/image/6.png)<br/>**支持默认语言与多语言切换, 适合多用户环境** |

---

## ⚡ 快速开始

### 📦 安装

```shell
# 安装运行时依赖 (不包含构建翻译文件所需的额外依赖)
uv add easy-ai18n

# 添加翻译构建工具依赖到开发依赖
uv add --dev "easy-ai18n[builder]"

```

### 🧪 简单示例

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

## 📘 使用教程

### 🔎 语言选择器

语言选择器是 Easy AI18n 取用多语言结果的核心机制: 一次翻译同时得到所有语言, 再按需选择。它分两个方向:

- **前置选择器** `_['ja']("text")`: 先锁定语言, 再翻译文本 —— 适合固定语言的作用域 (如某个用户会话内的所有文本)
- **后置选择器** `_("text")['ja']` / `_("text")('ja')`: 先翻译得到 `LocaleContent`, 再从中取语言 —— 适合单次取用不同语言

翻译的产物是 **LocaleContent** `_("text")`: 以默认语言的字符串形式存在, 内部携带全部语言的翻译, 供后续按需取用

不指定语言时返回默认语言文本 (默认即源语言 `source_locale`, 源语言没有翻译文件, 直接返回原文; 可用 `default_locale`
覆盖); 选择器不限于语言代码: 自定义选择器可接收任意对象 (如 Telegram 的 `Message`), 从中解析用户语言, 实现多用户场景的动态切换

所有写法的样子与类型如下:

```python
_ = i18n.i18n()  # I18n: 翻译函数

_t: PreLocaleSelector = _['ja']  # 前置选择器: 锁定语言 (不指定则为 str 语言代码)
_t("text")  # 前置选择器调用
_['ja']("text")  # 等价写法 (不绑定变量)

content: LocaleContent = _("text")  # 多语言对象: 默认语言的字符串, 内含所有语言
content['ja']  # 后置选择器 (下标取语言)
content('ja')  # 后置选择器 (调用取语言, 等价下标)
_("text")['ja']  # 等价写法 (不绑定变量)
```

示例:

```python
from easy_ai18n import EasyAI18n

i18n = EasyAI18n("en", func_names=['_', '_t'])
_ = i18n.i18n()
_t = _['ja']  # 前置选择器: 锁定日文

d = {
    1: _('apple'),  # 默认语言 (源语言 en) -> 原文
    2: _('banana'),
    3: _t('orange'),  # 前置选择器 -> 日文
}
print(d[1]['zh-hans'])  # 后置选择器: 取简体中文  output: 苹果
print(d[2])  # 默认语言输出            output: banana
print(d[3])  # 前置选择器输出          output: みかん
```

**默认语言覆盖**:

```python
_ = i18n.i18n(default_locale="ja")
print(_('apple'))  # 默认语言为 ja, 直接输出日文
```

### ⚙️ 构建选项

`build()` 支持控制提取范围与并发行为:

```python
i18n.build(
    to_locales=["ja", "ru"],
    project_root="./",  # 扫描根目录 (默认当前工作目录; include/exclude 相对它解析)
    include=["src/**"],  # 只提取匹配的文件/目录 (支持 glob)
    exclude=["tests/**", "build/**"],  # 排除文件或目录 (默认已排除 .venv/.git/.idea)
    concurrent_locales=False,  # 语言间并发翻译 (默认 True; 免费/限流 API 建议关闭)
    max_retries=3,  # 单语言失败后的额外重试次数 (默认 2)
)
```

**自定义翻译文件目录**: 默认生成在 `./i18n`, 可通过 `locales_dir` 修改:

```python
i18n = EasyAI18n("en", locales_dir="./locales")
```

### 📝 字符串格式化与变量插值

完整支持 f-string 变量插值与所有 Python 格式化语法

```python
from easy_ai18n import EasyAI18n

i18n = EasyAI18n("en")
_ = i18n.i18n()

name = "Alice"
count = 3

print(_(f"Hello, {name}!")['zh-hans'])  # output: 你好, Alice!
print(_(f"Count: {count:02d}")['zh-hans'])  # output: 数量: 03
print(_(f"Value: {count!r}")['zh-hans'])  # output: 值: 3

# 多参数自动拼接 (默认以空格分隔)
print(_("Hello", "world")['zh-hans'])  # output: 你好 世界

# sep= 自定义分隔符 (也可在构造时全局设置: EasyAI18n("en", sep="-"))
print(_("Hello", "world", sep="-")['zh-hans'])  # output: 你好-世界
```

### 🛠️ 自定义翻译函数名称

```python
from easy_ai18n import EasyAI18n

i18n = EasyAI18n(
    "en",
    func_names=["_t", "_"]  # 自定义翻译函数名称
)

_t = i18n.i18n()
_ = _t

print(_t("Hello, world!"))
print(_("Hello, world!"))
```

### 🤖 使用 AI 进行翻译

**默认翻译器**: 不传 `translator` 时, `build()` 默认使用免费的 `GoogleTranslator`, 无需任何配置:

```python
i18n.build(to_locales=["ja"])  # 默认 GoogleTranslator
```

**两种 LLM 翻译模式**:

- 批量 `LLMBulkTranslator` 一次翻译多条文本
- 逐条 `LLMItemTranslator` 一次翻译一条文本

```python
from easy_ai18n import EasyAI18n
from easy_ai18n.translators import LLMBulkTranslator

translator = LLMBulkTranslator(api_key="...", base_url="...", model="gpt-5-mini")

i18n = EasyAI18n("en")
i18n.build(to_locales=["ru", "ja", "zh-hant"], translator=translator)

_ = i18n.i18n()

print(_("Hello, world!")['zh-hant'])
```

**自定义 Agent**: 两个 LLM 翻译器都支持传入任意 pydantic-ai Agent, 可接入本地模型或其他 provider:

```python
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider
from easy_ai18n.translators import LLMItemTranslator

agent = Agent(
    model=OpenAIChatModel(
        "qwen2.5:7b",  # 本地 Ollama 模型
        provider=OpenAIProvider(api_key="ollama", base_url="http://localhost:11434/v1"),
    ),
    output_type=str,  # 使用 LLMBulkTranslator 时需改为 list[TranslatorResult]
)

translator = LLMItemTranslator(agent=agent)
```

### 🛠️ 自定义翻译器

继承 `BaseTranslator` 并实现 `translate_chunk` 即可:

```python
from easy_ai18n import EasyAI18n, TextMap
from easy_ai18n.translators import BaseTranslator


class MyTranslator(BaseTranslator):
    async def translate_chunk(self, *, texts: TextMap, target_lang: str, source_lang: str) -> TextMap:
        # 实现翻译逻辑
        ...


i18n = EasyAI18n("zh-hans")
i18n.build(
    to_locales=["ja"],
    translator=MyTranslator(),
)
```

### 👥 多用户语言场景 (如 Telegram Bot)

通过自定义语言选择器, 在多用户环境中实现动态语言选择:

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

## 📂 示例项目

**使用 Easy AI18n 的真实项目**

- **[z-mio/parse_hub_bot](https://github.com/z-mio/parse_hub_bot)**

## 🗂️ 项目结构

```text
easy_ai18n
├── __init__.py          # EasyAI18n 入口 + 公开 API
├── i18n.py              # 翻译运行时(I18n, Pre/PostLocaleSelector, LocaleContent)
├── translators.py       # 翻译器(ABC + GoogleTranslator + LLM*Translator)
├── errors.py            # 异常类
├── py.typed             # PEP 561 类型标记
├── _builder.py          # 构建器: 提取, 翻译, 生成 YAML 文件
├── _parser.py           # AST 语法树解析器
├── _progress.py         # 进度展示 (rich 进度条 / 非终端降级为行式报告)
├── _loader.py           # 加载器: 加载翻译文件
└── _types.py            # Text/TextId/TextMap 类型定义
```

## 📜 开源协议

本项目基于 [MIT License](LICENSE) 开源

---

<div align="center">

**如果这个项目对你有帮助，欢迎点个 ⭐ Star!**

</div>
