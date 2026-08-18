<div align="center">

<a href="https://github.com/z-mio/easy-ai18n">
    <img src="docs/image/logo.png" width="100" alt="icon">
</a>

**シンプルでエレガントな Python3 国際化 (i18n) ライブラリ**

[![Python](https://img.shields.io/badge/python-3.12+-yellow)](https://www.python.org/)
[![GitHub stars](https://img.shields.io/github/stars/z-mio/easy-ai18n.svg?style=social&label=Stars)](https://github.com/z-mio/easy-ai18n)
[![GitHub forks](https://img.shields.io/github/forks/z-mio/easy-ai18n.svg?style=social&label=Forks)](https://github.com/z-mio/easy-ai18n)
[![PyPI version](https://badge.fury.io/py/easy-ai18n.svg)](https://badge.fury.io/py/easy-ai18n)
[![GitHub License](https://img.shields.io/github/license/z-mio/easy-ai18n)](https://github.com/z-mio/easy-ai18n/blob/master/LICENSE)

**[English](https://github.com/z-mio/easy-ai18n) | [中文](README.zh.md) | 日本語**

</div>

# 🌍 Easy AI18n

Easy AI18n は、AI 翻訳、マルチユーザーシナリオ、そして完全な文字列フォーマット構文をサポートするモダンな Python3
国際化ライブラリで、プロジェクトのグローバル化をより優雅で自然なものにします。

## ✨ 主な特徴:

- **🚀 シンプルで使いやすい:** 数行のコードでプロジェクトの国際化を簡単に実現
- **✨ 構文が優雅:** 既存のコードに自然に溶け込む
- **🤖 AI 翻訳:** 大規模言語モデル (LLM) による翻訳をサポートし、高品質な結果を保証
- **📝 フォーマット互換:** Python のすべての文字列フォーマット構文を完全サポート
- **🌐 動的多言語:** 実行時に動的に言語を選択できる

## 🔍 他の i18n ツールとの比較

|                                             他の i18n ツール                                             |                                             EasyAI18n                                              |
|:--------------------------------------------------------------------------------------------------------:|:--------------------------------------------------------------------------------------------------:|
|         ![](docs/image/1.png)<br/>**`key` と i18n ファイルの手動管理が必要で、開発コストが高い**         |            ![](docs/image/2.png)<br/>**翻訳内容を自動抽出し、ファイルの手動管理は不要**            |
|                     ![](docs/image/3.png)<br/>**一部のフォーマット構文のみサポート**                     |                ![](docs/image/4.png)<br/>**すべてのフォーマット構文を完全サポート**                |
| ![](docs/image/5.png)<br/>**実行時の多言語切り替えには対応しておらず、マルチユーザーシナリオには不向き** | ![](docs/image/6.png)<br/>**デフォルト言語と多言語切り替えをサポートし、マルチユーザー環境に最適** |

---

## ⚡ クイックスタート

### 📦 インストール

```shell
# ランタイム依存関係をインストール (翻訳ファイルのビルドに必要な追加依存関係は含まない)
uv add easy-ai18n

# 翻訳ビルドツールの依存関係を開発用依存関係に追加
uv add --dev "easy-ai18n[builder]"

```

### 🧪 簡単な例

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

## 📘 使い方ガイド

### 🔎 言語セレクター

言語セレクターは Easy AI18n が多言語の結果を取り出すための核心的な仕組みです: 一度の翻訳で全言語を同時に取得し、必要に応じて選択します。方向は
2 つあります:

- **前置セレクター** `_['ja']("text")`: 先に言語をロックしてからテキストを翻訳します —— 固定言語のスコープ (例:
  あるユーザーセッション内のすべてのテキスト) に適しています
- **後置セレクター** `_("text")['ja']` / `_("text")('ja')`: 先に翻訳して `LocaleContent`
  を取得し、そこから言語を取り出します —— 単発で異なる言語を取得する場合に適しています

翻訳の成果物は **LocaleContent** `_("text")` です: デフォルト言語の文字列として存在し、内部に全言語の翻訳を保持しているので、後で必要に応じて取り出せます

言語を指定しない場合はデフォルト言語のテキストを返します (デフォルトはソース言語 `source_locale`
で、ソース言語には翻訳ファイルがないため原文をそのまま返します; `default_locale` で上書き可能);
セレクターは言語コードに限定されません: カスタムセレクターは任意のオブジェクト (例: Telegram の `Message`)
を受け取り、そこからユーザーの言語を解析して、マルチユーザーシナリオでの動的な切り替えを実現できます

すべての書き方とその型は次のとおりです:

```python
_ = i18n.i18n()  # I18n: 翻訳関数

_t: PreLocaleSelector = _['ja']  # 前置セレクター: 言語をロック (指定しない場合は str 言語コード)
_t("text")  # 前置セレクターの呼び出し
_['ja']("text")  # 等価な書き方 (変数にバインドしない)

content: LocaleContent = _("text")  # 多言語オブジェクト: デフォルト言語の文字列で、全言語を含む
content['ja']  # 後置セレクター (添字で言語を取得)
content('ja')  # 後置セレクター (呼び出しで言語を取得、添字と等価)
_("text")['ja']  # 等価な書き方 (変数にバインドしない)
```

例:

```python
from easy_ai18n import EasyAI18n

i18n = EasyAI18n("en", func_names=['_', '_t'])
_ = i18n.i18n()
_t = _['ja']  # 前置セレクター: 日本語をロック

d = {
    1: _('apple'),  # デフォルト言語 (ソース言語 en) -> 原文
    2: _('banana'),
    3: _t('orange'),  # 前置セレクター -> 日本語
}
print(d[1]['zh-hans'])  # 後置セレクター: 簡体字中国語を取得  output: 苹果
print(d[2])  # デフォルト言語の出力            output: banana
print(d[3])  # 前置セレクターの出力          output: みかん
```

**デフォルト言語の上書き**:

```python
_ = i18n.i18n(default_locale="ja")
print(_('apple'))  # デフォルト言語が ja なので、日本語をそのまま出力
```

### ⚙️ ビルドオプション

`build()` は抽出範囲と並行挙動を制御できます:

```python
i18n.build(
    to_locales=["ja", "ru"],
    project_root="./",  # スキャンルートディレクトリ (デフォルトは現在の作業ディレクトリ; include/exclude はこれに対する相対パスで解決)
    include=["src/**"],  # 一致するファイル/ディレクトリのみ抽出 (glob 対応)
    exclude=["tests/**", "build/**"],  # ファイルまたはディレクトリを除外 (デフォルトで .venv/.git/.idea は除外済み)
    concurrent_locales=False,  # 言語間の並行翻訳 (デフォルトは True; 無料/レート制限付き API ではオフ推奨)
    max_retries=3,  # 単一言語の失敗後の追加リトライ回数 (デフォルトは 2)
)
```

**翻訳ファイルディレクトリのカスタマイズ**: デフォルトでは `./i18n` に生成されます。`locales_dir` で変更できます:

```python
i18n = EasyAI18n("en", locales_dir="./locales")
```

### 📝 文字列フォーマットと変数補間

f-string の変数補間とすべての Python フォーマット構文を完全サポート

```python
from easy_ai18n import EasyAI18n

i18n = EasyAI18n("en")
_ = i18n.i18n()

name = "Alice"
count = 3

print(_(f"Hello, {name}!")['zh-hans'])  # output: 你好, Alice!
print(_(f"Count: {count:02d}")['zh-hans'])  # output: 数量: 03
print(_(f"Value: {count!r}")['zh-hans'])  # output: 值: 3

# 複数の引数を自動連結 (デフォルトではスペース区切り)
print(_("Hello", "world")['zh-hans'])  # output: 你好 世界

# sep= でカスタム区切り文字 (コンストラクタでグローバル設定も可能: EasyAI18n("en", sep="-"))
print(_("Hello", "world", sep="-")['zh-hans'])  # output: 你好-世界
```

### 🛠️ カスタム翻訳関数名

```python
from easy_ai18n import EasyAI18n

i18n = EasyAI18n(
    "en",
    func_names=["_t", "_"]  # カスタム翻訳関数名
)

_t = i18n.i18n()
_ = _t

print(_t("Hello, world!"))
print(_("Hello, world!"))
```

### 🤖 AI による翻訳

**デフォルト翻訳器**: `translator` を渡さない場合、`build()` はデフォルトで無料の `GoogleTranslator`
を使用します。設定は一切不要です:

```python
i18n.build(to_locales=["ja"])  # デフォルトの GoogleTranslator
```

**2 種類の LLM 翻訳モード**:

- 一括 `LLMBulkTranslator`: 一度に複数のテキストを翻訳
- 個別 `LLMItemTranslator`: 一度に 1 つのテキストを翻訳

```python
from easy_ai18n import EasyAI18n
from easy_ai18n.translators import LLMBulkTranslator

translator = LLMBulkTranslator(api_key="...", base_url="...", model="gpt-5-mini")

i18n = EasyAI18n("en")
i18n.build(to_locales=["ru", "ja", "zh-hant"], translator=translator)

_ = i18n.i18n()

print(_("Hello, world!")['zh-hant'])
```

**カスタム Agent**: 2 つの LLM 翻訳器はどちらも任意の pydantic-ai Agent を渡すことをサポートしており、ローカルモデルや他の
provider にも接続できます:

```python
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider
from easy_ai18n.translators import LLMItemTranslator

agent = Agent(
    model=OpenAIChatModel(
        "qwen2.5:7b",  # ローカル Ollama モデル
        provider=OpenAIProvider(api_key="ollama", base_url="http://localhost:11434/v1"),
    ),
    output_type=str,  # LLMBulkTranslator を使用する場合は list[TranslatorResult] に変更する必要があります
)

translator = LLMItemTranslator(agent=agent)
```

### 🛠️ カスタム翻訳器

`BaseTranslator` を継承して `translate_chunk` を実装するだけです:

```python
from easy_ai18n import EasyAI18n, TextMap
from easy_ai18n.translators import BaseTranslator


class MyTranslator(BaseTranslator):
    async def translate_chunk(self, *, texts: TextMap, target_lang: str, source_lang: str) -> TextMap:
        # 翻訳ロジックを実装
        ...


i18n = EasyAI18n("zh-hans")
i18n.build(
    to_locales=["ja"],
    translator=MyTranslator(),
)
```

### 👥 マルチユーザー言語対応 (例: Telegram Bot)

カスタム言語セレクターを使用して、マルチユーザー環境で動的な言語選択を実現します:

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

## 📂 サンプルプロジェクト

**Easy AI18n を使用した実際のプロジェクト**

- **[z-mio/parse_hub_bot](https://github.com/z-mio/parse_hub_bot)**

## 🗂️ プロジェクト構成

```text
easy_ai18n
├── __init__.py          # EasyAI18n のエントリポイント + 公開 API
├── i18n.py              # 翻訳ランタイム(I18n, Pre/PostLocaleSelector, LocaleContent)
├── translators.py       # 翻訳器(ABC + GoogleTranslator + LLM*Translator)
├── errors.py            # 例外クラス
├── py.typed             # PEP 561 型マーカー
├── _builder.py          # ビルダー: 抽出、翻訳、YAML ファイルの生成
├── _parser.py           # AST 構文木パーサー
├── _progress.py         # 進捗表示 (rich プログレスバー / 非ターミナルでは行形式レポートにフォールバック)
├── _loader.py           # ローダー: 翻訳ファイルの読み込み
└── _types.py            # Text/TextId/TextMap 型定義
```

## 📜 ライセンス

このプロジェクトは [MIT License](LICENSE) の下で公開されています

---

<div align="center">

**このプロジェクトが役に立ったなら、⭐ Star をお願いします！**

</div>
