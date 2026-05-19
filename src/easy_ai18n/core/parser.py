"""
AST 解析器
获取调用函数的代码块 -> 转为 AST 节点 -> 遍历 AST 节点 -> 提取指定函数调用的节点 -> 提取字符串和变量 -> 处理变量 -> 返回结果
"""  # noqa: E501

from __future__ import annotations

import ast
import inspect
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from types import FrameType
from typing import Any

from ..error import EvaluateError, FormatError, UnsupportedSyntaxError


@dataclass
class StringData:
    string: str
    variables: dict[str, object]
    call_node: ast.Call


class CallVisitor(ast.NodeVisitor):
    def __init__(self, func_names: list[str]):
        self.func_names = func_names
        self.nodes: list[ast.Call] = []

    def visit_Call(self, node: ast.Call) -> None:
        func = node.func
        # 后置选择器: _()
        if isinstance(func, ast.Name) and func.id in self.func_names:
            self.nodes.append(node)
        # 后置选择器: obj._()
        elif isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name) and func.attr in self.func_names:
            self.nodes.append(node)
        # 前置选择器: _[]()
        elif isinstance(func, ast.Subscript) and isinstance(func.value, ast.Name) and func.value.id in self.func_names:
            new_call = ast.Call(
                func=func.slice,
                args=node.args,
                keywords=node.keywords,
            )
            self.nodes.append(new_call)
        # 前置选择器: obj._[]()
        elif (
            isinstance(func, ast.Subscript)
            and isinstance(func.value, ast.Attribute)
            and func.value.attr in self.func_names
        ):
            new_call = ast.Call(
                func=func.slice,
                args=node.args,
                keywords=node.keywords,
            )
            self.nodes.append(new_call)
        # 深入其他可能的子节点
        self.generic_visit(node)


class UnsupportedSyntaxValidator:
    def __init__(self, source_path: Path | None = None, source: str | None = None):
        self.source_path = source_path
        self.source_lines = source.splitlines() if source else []

    def validate_call(self, call_node: ast.Call) -> None:
        for node in call_node.args:
            self._validate_node(node)
        for keyword in call_node.keywords:
            self._validate_node(keyword.value)

    def _validate_node(self, node: ast.AST) -> None:
        for sub_node in ast.walk(node):
            if not isinstance(sub_node, ast.JoinedStr):
                continue
            for value in sub_node.values:
                if not isinstance(value, ast.FormattedValue):
                    continue
                if any(isinstance(child, ast.Await) for child in ast.walk(value.value)):
                    self._raise_unsupported(value.value)

    def _raise_unsupported(self, node: ast.AST) -> None:
        location = self._location(node)
        message = f"构建失败: 不支持在 f-string 中使用 await{location}\n请先执行 await，再将结果传入 f-string。"
        raise UnsupportedSyntaxError(message)

    def _location(self, node: ast.AST) -> str:
        lineno = getattr(node, "lineno", None)
        col_offset = getattr(node, "col_offset", None)
        if not self.source_path or lineno is None or col_offset is None:
            return ""
        line = ""
        if self.source_lines and lineno <= len(self.source_lines):
            line = self.source_lines[lineno - 1].strip()
        location = f"\nfile: {self.source_path}:{lineno}:{col_offset + 1}"
        return f"{location}\ncode: {line}" if line else location


class StringConstructor:
    """
    根据传入的 AST 节点构造字符串，同时处理 f-string 表达式。
    """

    def __init__(self, sep: str, func_names: list[str]):
        self.sep = sep
        self.func_names = func_names

    def construct_from_node(
        self,
        call_node: ast.Call,
        evaluator: VariableEvaluator | None = None,
    ) -> tuple[str, dict[str, object]]:
        sep = self.sep
        for kw in call_node.keywords:
            if kw.arg == "sep" and isinstance(kw.value, ast.Constant):
                sep = str(kw.value.value)
                break

        raw_parts: list[str] = []
        variables: dict[str, object] = {}

        for arg in call_node.args:
            if isinstance(arg, ast.Constant):
                # 常量字符串直接添加
                raw_parts.append(str(arg.value))
            else:
                if isinstance(arg, ast.JoinedStr):
                    part, found = self._handle_f_string(arg, evaluator)
                else:
                    # 将其他表达式包装为 f-string
                    expr_src = ast.unparse(arg)
                    wrapper = f'{self.func_names[0]}(f"{{{expr_src}}}")'
                    wrapper_expr = ast.parse(wrapper).body[0]
                    if not isinstance(wrapper_expr, ast.Expr) or not isinstance(wrapper_expr.value, ast.Call):
                        continue
                    wrapper_arg = wrapper_expr.value.args[0]
                    if not isinstance(wrapper_arg, ast.JoinedStr):
                        continue
                    part, found = self._handle_f_string(wrapper_arg, evaluator)

                raw_parts.append(part)
                variables.update(found)
        if r := sep.join(raw_parts):
            return r, variables
        return "", {}

    def _handle_f_string(
        self,
        node: ast.JoinedStr,
        evaluator: VariableEvaluator | None = None,
    ) -> tuple[str, dict[str, object]]:
        """
        :param node:
        :param evaluator: 为 Noe 则只提取表达式, 不求值
        :return:
        """
        parts: list[str] = []
        variables: dict[str, object] = {}
        for value in node.values:
            if isinstance(value, ast.Constant):
                parts.append(str(value.value))
            elif isinstance(value, ast.FormattedValue):
                expr = ast.unparse(value.value)
                # 获取转换标志
                conversion = self._handle_conversion(value.conversion)
                # 获取格式说明符
                format_spec = self._handle_format_spec(value.format_spec, evaluator)
                # 构建格式化表达式
                expr_ = (
                    f"{{{expr}{('!' + conversion) if conversion else ''}{(':' + format_spec) if format_spec else ''}}}"
                )

                parts.append(expr_)

                variables[expr_] = evaluator.evaluate(expr, conversion, format_spec) if evaluator else None
        return "".join(parts), variables

    @staticmethod
    def _handle_conversion(conversion: int) -> str | None:
        """
        处理转换标志
        :param conversion:
        :return:
        """
        return {97: "a", 114: "r", 115: "s"}[conversion] if conversion != -1 else None

    def _handle_format_spec(
        self,
        format_spec: ast.expr | None,
        evaluator: VariableEvaluator | None,
    ) -> str | None:
        """
        处理格式说明符
        :param format_spec:
        :param evaluator:
        :return:
        """
        if not format_spec:
            return None

        if isinstance(format_spec, ast.JoinedStr):
            spec_str, _ = self._handle_f_string(format_spec, evaluator)
            return spec_str
        elif isinstance(format_spec, ast.Constant):
            return str(format_spec.value)
        else:
            return None


class VariableEvaluator:
    def __init__(self, globals_dict: dict[str, Any], locals_dict: dict[str, Any]):
        self.globals = globals_dict
        self.locals = locals_dict

    def evaluate(self, expr: str, conversion: str | None = None, format_spec: str | None = None) -> object:
        """
        对表达式进行求值

        Args:
            expr: 要求值的表达式
            conversion: 转换标志 ('s', 'r', 'a')
            format_spec: 格式说明符

        Returns:
            求值结果
        """
        try:
            # 计算基本值
            value = self._evaluate_basic(expr)
            # 应用转换标志
            if conversion:
                value = self._apply_conversion(value, conversion)

            # 应用格式说明符
            if not format_spec:
                return value
            try:
                # 如果格式说明符包含表达式，先求值
                format_spec = self._eval_format_spec(format_spec)
                return format(value, format_spec)
            except Exception as e:
                raise FormatError(e) from e
        except Exception as e:
            raise EvaluateError(e) from e

    def _evaluate_basic(self, expr: str) -> object:
        """基础求值"""
        if expr.isidentifier():
            # 简单变量查找
            return self.locals.get(expr, self.globals.get(expr, None))
        else:
            # 复杂表达式求值
            compiled_expr = compile(
                expr,
                "<string>",
                "eval",
                # flags=ast.PyCF_ALLOW_TOP_LEVEL_AWAIT,
            )
            return eval(compiled_expr, self.globals, self.locals)

    @staticmethod
    def _apply_conversion(value: object, conversion: str) -> object:
        """应用转换标志"""
        if conversion == "s":
            return str(value)
        elif conversion == "r":
            return repr(value)
        elif conversion == "a":
            return ascii(value)
        return value

    def _eval_format_spec(self, format_spec: str) -> str:
        if "{" in format_spec:
            format_parts = []
            current = ""
            in_expr = False

            for char in format_spec:
                if char == "{":
                    if current:
                        format_parts.append(current)
                    current = ""
                    in_expr = True
                elif char == "}" and in_expr:
                    if current:
                        format_parts.append(str(self._evaluate_basic(current)))
                    current = ""
                    in_expr = False
                else:
                    current += char

            if current:
                format_parts.append(current)

            return "".join(format_parts)
        return format_spec


class ASTParser:
    def __init__(self, sep: str, func_names: list[str]):
        self.sep = sep
        self.func_names = func_names

    @staticmethod
    @cache
    def _read_file_bytes(filename: str) -> list[bytes]:
        """按行读取并缓存源文件的字节内容"""
        with open(filename, "rb") as f:
            return f.read().splitlines(keepends=True)

    def get_code_block(self, frame: FrameType) -> str:
        # 获取位置属性，跳过上下文行
        info = inspect.getframeinfo(frame, context=0).positions
        if not info or info.lineno is None or info.end_lineno is None:
            return ""
        if info.col_offset is None or info.end_col_offset is None:
            return ""
        filename = frame.f_code.co_filename
        lineno = info.lineno - 1
        end_lineno = info.end_lineno - 1
        col_start = info.col_offset
        col_end = info.end_col_offset

        # 按字节读取并缓存
        lines_bytes = self._read_file_bytes(filename)

        # 单行 vs 多行
        if lineno == end_lineno:
            return lines_bytes[lineno][col_start:col_end].decode("utf-8")

        # 多行拼接与分段解码
        parts = [lines_bytes[lineno][col_start:]]
        parts.extend(lines_bytes[lineno + 1 : end_lineno])
        parts.append(lines_bytes[end_lineno][:col_end])
        return "".join(segment.decode("utf-8") for segment in parts)

    def extract_all(
        self,
        *,
        node: ast.AST,
        source_path: Path | None = None,
        source: str | None = None,
    ) -> list[StringData]:
        """
        仅提取解析后的字符串，默认只解析第一个匹配的调用节点。
        """
        target_nodes = self.get_target_nodes(node)
        if not target_nodes:
            return []

        results = []
        validator = UnsupportedSyntaxValidator(source_path, source)
        string_constructor = StringConstructor(sep=self.sep, func_names=self.func_names)
        for call_node in target_nodes:
            validator.validate_call(call_node)
            constructed, vars_found = string_constructor.construct_from_node(call_node, None)
            results.append(StringData(constructed, vars_found, call_node))
        return results

    def extract(
        self,
        *,
        frame: FrameType | None = None,
        call_node: ast.Call | None = None,
    ) -> StringData | None:
        """
        解析第一个匹配的调用节点，并返回构造后的字符串及变量数据。
        """
        # 节点解析的性能开销大, 尽量使用缓存
        if call_node is None:
            if frame is None:
                return None
            call_text = self.get_code_block(frame)
            node = ast.parse(call_text.strip())
            target_nodes = self.get_target_nodes(node)
            if not target_nodes:
                return None
            call_node = target_nodes[0]

        string_constructor = StringConstructor(sep=self.sep, func_names=self.func_names)
        constructed, vars_found = string_constructor.construct_from_node(
            call_node,
            VariableEvaluator(frame.f_globals, frame.f_locals) if frame else None,
        )
        return StringData(constructed, vars_found, call_node)

    def get_target_nodes(self, node: ast.AST) -> list[ast.Call]:
        visitor = CallVisitor(self.func_names)
        visitor.visit(node)
        return visitor.nodes
