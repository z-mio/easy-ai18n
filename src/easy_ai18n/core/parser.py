"""
AST 解析器
获取调用函数的代码块 -> 转为 AST 节点 -> 遍历 AST 节点 -> 提取指定函数调用的节点 -> 提取字符串和变量 -> 处理变量 -> 返回结果
"""

import ast
import inspect
from dataclasses import dataclass
from functools import lru_cache
from types import FrameType

from ..error import FormatError, EvaluateError


@dataclass
class StringData:
    string: str
    variables: dict
    call_node: ast.Call


class CallVisitor(ast.NodeVisitor):
    def __init__(self, i18n_function_names: list[str]):
        self.i18n_function_names = i18n_function_names
        self.nodes: list[ast.Call] = []

    def visit_Call(self, node: ast.Call):
        func = node.func
        # 后置选择器：_()
        if isinstance(func, ast.Name) and func.id in self.i18n_function_names:
            self.nodes.append(node)
        # 前置选择器：_[]()
        elif isinstance(func, ast.Subscript):
            if (
                isinstance(func.value, ast.Name)
                and func.value.id in self.i18n_function_names
            ):
                new_call = ast.Call(
                    func=func.slice,
                    args=node.args,
                    keywords=node.keywords,
                )
                self.nodes.append(new_call)
        # 深入其他可能的子节点
        self.generic_visit(node)


class StringConstructor:
    """
    根据传入的 AST 节点构造字符串，同时处理 f-string 表达式。
    """

    def __init__(self, sep: str, i18n_function_names: list[str]):
        self.sep = sep
        self.i18n_function_names = i18n_function_names

    def construct_from_node(
        self, call_node: ast.Call, evaluator: "VariableEvaluator" = None
    ) -> tuple[str, dict]:
        sep = next(
            (
                kw.value.value
                for kw in call_node.keywords
                if kw.arg == "sep" and isinstance(kw.value, ast.Constant)
            ),
            self.sep,
        )

        raw_parts: list[str] = []
        variables: dict = {}

        for arg in call_node.args:
            if isinstance(arg, ast.Constant):
                # 常量字符串直接添加
                raw_parts.append(arg.value)
            else:
                if isinstance(arg, ast.JoinedStr):
                    part, found = self._handle_f_string(arg, evaluator)
                else:
                    # 将其他表达式包装为 f-string
                    expr_src = ast.unparse(arg)  # type: ignore
                    wrapper = f'{self.i18n_function_names[0]}(f"{{{expr_src}}}")'
                    wrapper_call: ast.Call = ast.parse(wrapper).body[0].value  # type: ignore
                    part, found = self._handle_f_string(wrapper_call.args[0], evaluator)  # type: ignore

                raw_parts.append(part)
                variables.update(found)
        if r := sep.join(raw_parts):
            return r, variables
        return "", {}

    def _handle_f_string(
        self, node: ast.JoinedStr, evaluator: "VariableEvaluator" = None
    ) -> tuple[str, dict]:
        """
        :param node:
        :param evaluator: 为 Noe 则只提取表达式, 不求值
        :return:
        """
        parts = []
        variables = {}
        for value in node.values:
            if isinstance(value, ast.Constant):
                parts.append(value.value)
            elif isinstance(value, ast.FormattedValue):
                expr = ast.unparse(value.value)
                # 获取转换标志
                conversion = self._handle_conversion(value.conversion)
                # 获取格式说明符
                format_spec = self._handle_format_spec(value.format_spec, evaluator)
                # 构建格式化表达式
                expr_ = f"{{{expr}{('!' + conversion) if conversion else ''}{(':' + format_spec) if format_spec else ''}}}"

                parts.append(expr_)

                variables[expr_] = (
                    evaluator.evaluate(expr, conversion, format_spec)
                    if evaluator
                    else None
                )
        return "".join(parts), variables

    @staticmethod
    def _handle_conversion(conversion):
        """
        处理转换标志
        :param conversion:
        :return:
        """
        return {97: "a", 114: "r", 115: "s"}[conversion] if conversion != -1 else None

    def _handle_format_spec(
        self,
        format_spec,
        evaluator,
    ):
        """
        处理格式说明符
        :param format_spec:
        :param evaluator:
        :return:
        """
        if not format_spec:
            return None

        if isinstance(format_spec, ast.JoinedStr):
            spec_str, spec_vars = self._handle_f_string(format_spec, evaluator)
            return spec_str
        elif isinstance(format_spec, ast.Constant):
            return format_spec.value
        else:
            return None


class VariableEvaluator:
    def __init__(self, globals_dict: dict, locals_dict: dict):
        self.globals = globals_dict
        self.locals = locals_dict

    def evaluate(
        self, expr: str, conversion: str = None, format_spec: str = None
    ) -> any:
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

    def _evaluate_basic(self, expr: str) -> any:
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
    def _apply_conversion(value: any, conversion: str) -> str:
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
    def __init__(self, sep: str, i18n_function_names: list[str]):
        self.sep = sep
        self.i18n_function_names = i18n_function_names

    @staticmethod
    @lru_cache(maxsize=None)
    def _read_file_bytes(filename: str) -> list[bytes]:
        """按行读取并缓存源文件的字节内容"""
        with open(filename, "rb") as f:
            return f.read().splitlines(keepends=True)

    def get_code_block(self, frame: FrameType) -> str:
        # 获取位置属性，跳过上下文行
        info = inspect.getframeinfo(frame, context=0).positions
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

    def extract_all(self, *, node: ast.AST) -> list[StringData]:
        """
        仅提取解析后的字符串，默认只解析第一个匹配的调用节点。
        """
        target_nodes = self.get_target_nodes(node)
        if not target_nodes:
            return []

        results = []
        string_constructor = StringConstructor(
            sep=self.sep, i18n_function_names=self.i18n_function_names
        )
        for call_node in target_nodes:
            constructed, vars_found = string_constructor.construct_from_node(
                call_node, None
            )
            results.append(StringData(constructed, vars_found, call_node))
        return results

    def extract(
        self,
        *,
        frame: FrameType = None,
        call_node: ast.Call = None,
    ) -> StringData | None:
        """
        解析第一个匹配的调用节点，并返回构造后的字符串及变量数据。
        """
        # 节点解析的性能开销大, 尽量使用缓存
        if not call_node:
            call_text = self.get_code_block(frame)
            node = ast.parse(call_text.strip())
            target_nodes = self.get_target_nodes(node)
            if target_nodes:
                call_node = target_nodes[0]
            else:
                return None

        string_constructor = StringConstructor(
            sep=self.sep, i18n_function_names=self.i18n_function_names
        )
        constructed, vars_found = string_constructor.construct_from_node(
            call_node,
            VariableEvaluator(frame.f_globals, frame.f_locals) if frame else None,
        )
        return StringData(constructed, vars_found, call_node)

    def get_target_nodes(self, node: ast.AST) -> list[ast.Call]:
        visitor = CallVisitor(self.i18n_function_names)
        visitor.visit(node)
        return visitor.nodes
