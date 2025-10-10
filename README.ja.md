<div align="center">

<a href="https://github.com/z-mio/easy-ai18n">
    <img src="docs/image/logo.png" width="100" alt="icon">
</a>

**シンプルでエレガントな Python3 国際化 (i18n) ツール**

[![Python](https://img.shields.io/badge/python-3.12+-yellow)](https://www.python.org/)
[![GitHub stars](https://img.shields.io/github/stars/z-mio/easy-ai18n.svg?style=social&label=Stars)](https://github.com/z-mio/easy-ai18n)
[![GitHub forks](https://img.shields.io/github/forks/z-mio/easy-ai18n.svg?style=social&label=Forks)](https://github.com/z-mio/easy-ai18n)
[![PyPI version](https://badge.fury.io/py/easy-ai18n.svg)](https://badge.fury.io/py/easy-ai18n)
[![GitHub License](https://img.shields.io/github/license/z-mio/easy-ai18n)](https://github.com/z-mio/easy-ai18n/blob/master/LICENSE)

[English](https://github.com/z-mio/easy-ai18n) | [中文](README.zh.md) | 日本語

</div>

# 🌍 Easy AI18n

Easy AI18n は、Python3 向けのモダンな国際化ツールライブラリです。AI 翻訳、マルチユーザーシナリオ、完全な文字列フォーマット構文をサポートし、プロジェクトのグローバル化をよりエレガントかつ自然に実現します。

## ✨ 主な特徴:

- **🚀 簡単で使いやすい:** 数行のコードで国際化を実現
- **✨ エレガントな構文:** 翻訳対象のテキストを `_()` で囲むことで、コードに自然に統合
- **🤖 AI 翻訳:** 大規模言語モデル (LLM) を使った高品質な翻訳に対応
- **📝 フォーマット完全対応:** Python のすべての文字列フォーマット構文を完全サポート
- **🌐 多言語対応:** `[]` 言語セレクターで多言語を選択可能

## 🔍 他の i18n ツールとの比較

|                              他の i18n ツール                              |                             EasyAI18n                              |
|:---------------------------------------------------------------------:|:------------------------------------------------------------------:|
| ![](docs/image/1.png)<br/>**`key` と i18n ファイルを手動で管理する必要があり、開発コストが高い** |          ![](docs/image/2.png)<br/>**翻訳内容を自動抽出、ファイル管理不要**          |
|             ![](docs/image/3.png)<br/>**一部のフォーマット構文のみ対応**             |          ![](docs/image/4.png)<br/>**すべてのフォーマット構文に完全対応**           |
|     ![](docs/image/5.png)<br/>**リアルタイムの多言語切り替えができず、マルチユーザーに不向き**      | ![](docs/image/6.png)<br/>**デフォルト言語と多言語切り替えをサポート、マルチユーザー環境にも適応可能** |

---

## ⚡ クイックスタート

### 📦 インストール

```shell
pip install easy-ai18n
```

### 🧪 シンプルな例

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

## 🗂️ プロジェクト構成

```text
easy_ai18n
├── core                 # コア機能モジュール
│   ├── builder.py       # ビルダー：抽出、翻訳、YAMLファイルの生成
│   ├── i18n.py          # 翻訳の主なロジック
│   ├── loader.py        # ローダー：翻訳ファイルの読み込み
│   └── parser.py        # AST 構文解析器
├── prompts              # 翻訳用プロンプト
├── translator           # 翻訳モジュール
└── main.py              # エントリーポイント
```

## 📘 使い方ガイド

### 🛠️ 翻訳関数名のカスタマイズ

```python
from easy_ai18n import EasyAI18n

i18n = EasyAI18n(
    func_names=["_t", '_']  # カスタム翻訳関数名
)

_t = i18n.i18n()
_ = _t

print(_t("Hello, world!"))
print(_("Hello, world!"))
```

### 🤖 AI による翻訳の利用

```python
from easy_ai18n import EasyAI18n
from easy_ai18n.translator import OpenAIBulkTranslator

translator = OpenAIBulkTranslator(api_key=..., base_url=..., model='gpt-4o-mini')

i18n = EasyAI18n()
i18n.build(to_locales=["ru", "ja", 'zh-Hant'], translator=translator)

_ = i18n.i18n()

print(_("Hello, world!")['zh-Hant'])
```

### 🔎 言語セレクター

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

### 👥 マルチユーザー言語対応（例：Telegram Bot）

マルチユーザー環境で動的に言語を選択するには、カスタム言語セレクターを使用します：

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