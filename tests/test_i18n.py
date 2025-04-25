from src.easy_ai18n import EasyAI18n
import os

os.putenv("I18N_LOG_LEVEL", "DEBUG")
i18n = EasyAI18n()
_ = i18n.t()


def test_build():
    i18n.build(target_lang=["en", "ja"], include=["test_i18n.py"])
    assert i18n.i18n_file_dir.joinpath("en.yaml").exists()
    assert i18n.i18n_file_dir.joinpath("ja.yaml").exists()


def test_basic():
    # 普通测试
    assert _("你好, 世界") == "你好, 世界"
    assert _("你好", ", ", "世界")["ja"] == "こんにちは世界"
    assert int(_(1 + 1)) == 2

    # 使用方式
    # 前置语言选择器只能使用中括号, 后置语言选择器可以使用括号或中括号
    assert _["en"]("你好, 世界") == "Hello World"
    assert _("你好, 世界")["en"] == "Hello World"
    assert _("你好, 世界")("en") == "Hello World"

    # f-string 测试
    a, b = "你好", "世界"
    assert _["en"]("你好, 世界", f"{a}, {b}") == f"Hello, world {a}, {b}"

    # 连接符测试
    assert _["en"]("你好", b, sep="-") == f"Hello-{b}"

    # 字典&列表测试
    one = 1
    dict_test = {"a": _("hello"), "b": _("world"), "c": _(f"数字: {one}")}
    assert dict_test["a"] == "hello"
    assert dict_test["b"]["ja"] == "世界"
    assert dict_test["c"]["en"] == f"Number: {one}"

    list_test = [_("列表测试"), _(1 + 1)]
    assert list_test[0]["en"] == "List Test"
    assert int(list_test[1]) == 2

    dc_dict = {
        1: _("美国佛罗里达州迈阿密 🇺🇸\n🌏`149.154.175.53`"),
        2: _("荷兰阿姆斯特丹 🇳🇱\n🌏`149.154.167.51`"),
        3: _("美国佛罗里达州迈阿密 🇺🇸\n🌏`149.154.175.100`"),
        4: _("荷兰阿姆斯特丹 🇳🇱\n🌏`149.154.167.91`"),
        5: _("新加坡 🇸🇬\n🌏`91.108.56.130`"),
    }
    assert (
        dc_dict[3]["ja"]
        == """米国フロリダ州マイアミ🇺🇸
🌏`149.154.175.100`"""
    )

    # 多行测试
    vscode = "vscode"
    idea = "idea"
    vscode_en = f"""{vscode} is a young and ignorant girl. You have to teach her to learn, train her, and make her the most suitable for you.
{idea} is an intellectual and sensible sister who can help you do all the work"""
    vscode_ja = """VScodeは若くて無知な女の子です。あなたは彼女に学び、訓練し、彼女をあなたに最も適したものにするように教える必要があります。
アイデアは、あなたがすべての仕事をするのを助けることができる知的で賢明な姉妹です"""

    assert (
        _["en"](
            f"{vscode}是青春懵懂的少女，你要去教她学习，调教她，让她最适合你\n"
            f"{idea}是知性懂事的姐姐，她能帮你做完所有工作"
        )
        == vscode_en
    )

    assert (
        _(
            """vscode是青春懵懂的少女，你要去教她学习，调教她，让她最适合你
idea是知性懂事的姐姐，她能帮你做完所有工作"""
        )["ja"]
        == vscode_ja
    )

    assert (
        _(
            "vscode是青春懵懂的少女，你要去教她学习，调教她，让她最适合你",
            "idea是知性懂事的姐姐，她能帮你做完所有工作",
            sep=", ",
        )
        == "vscode是青春懵懂的少女，你要去教她学习，调教她，让她最适合你, idea是知性懂事的姐姐，她能帮你做完所有工作"
    )

    # 测试 f-string 各种格式化场景
    # 1. 数字格式化
    number = 3.14159
    assert str(_(f"{number:.2f}")) == "3.14"
    assert str(_(f"{number:10.2f}")) == "      3.14"
    assert str(_(f"{number:010.2f}")) == "0000003.14"

    # 2. 字符串对齐
    text = "hello"
    assert str(_(f"{text:>10}")) == "     hello"
    assert str(_(f"{text:<10}")) == "hello     "
    assert str(_(f"{text:^10}")) == "  hello   "

    # 3. 转换标志 - 注意这里的实际输出
    value = "世界"
    assert str(_(f"{value!s}")) == "世界"
    assert str(_(f"{value!r}")) == "'世界'"  # 不会带引号
    assert str(_(f"{value!a}")) == "'\\u4e16\\u754c'"  # 不会显示unicode转义

    # 4. 填充字符
    num = 42
    assert str(_(f"{num:*>5}")) == "***42"
    assert str(_(f"{num:0>5}")) == "00042"

    # 5. 整数格式
    number = 42
    assert str(_(f"{number:08d}")) == "00000042"
    assert str(_(f"{number:x}")) == "2a"
    assert str(_(f"{number:b}")) == "101010"
    assert str(_(f"{number:o}")) == "52"

    # 6. 百分比格式
    ratio = 0.25
    assert str(_(f"{ratio:.1%}")) == "25.0%"

    # 7. 组合使用 - 修正对齐的预期结果
    value = 123
    assert str(_(f"{value!r:>10}")) == "       123"  # 不会带引号的右对齐
    assert str(_(f"{value:0>10.2f}")) == "0000123.00"

    # 8. 动态宽度和精度
    width = 10
    precision = 2
    assert str(_(f"{number:{width}.{precision}f}")) == "     42.00"

    # 9. 表达式计算
    assert str(_(f"{1 + 2:03d}")) == "003"
    assert str(_(f"{len('hello'):02d}")) == "05"

    # 10. 特殊情况
    empty = ""
    assert str(_(f"{empty:>5}")) == "     "
    assert str(_(f"{None}")) == "None"
