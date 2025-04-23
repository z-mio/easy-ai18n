"""
AST 解析器
获取调用函数的代码块 -> 转为 AST 节点 -> 遍历 AST 节点 -> 提取指定函数调用的节点 -> 提取字符串和变量 -> 处理变量 -> 返回结果
"""

import ast
import inspect
import linecache
from dataclasses import dataclass
from types import FrameType

from ..config import ic
from ..error import FormatError, EvaluateError


@dataclass
class StringData:
    string: str
    variables: dict
    call_nodes: list[ast.Call]


class ASTWalker:
    """
    遍历 AST 并提取指定函数调用的节点。
    """

    @staticmethod
    def get_target_nodes(node: ast.AST) -> list[ast.Call]:
        target_nodes = []
        for item in ast.walk(node):
            if isinstance(item, ast.Call):
                # 后置语言选择器 _()[]
                if (
                    isinstance(item.func, ast.Name)
                    and item.func.id in ic.i18n_function_name
                ):
                    target_nodes.append(item)
                # 前置语言选择器 _[]()
                if (
                    isinstance(item.func, ast.Subscript)
                    and isinstance(item.func.value, ast.Name)
                    and item.func.value.id in ic.i18n_function_name
                ):
                    sub = item.func
                    target_nodes.append(
                        ast.Call(func=sub.slice, args=item.args, keywords=item.keywords)
                    )

        return target_nodes


class StringConstructor:
    """
    根据传入的 AST 节点构造字符串，同时处理 f-string 表达式。
    """

    def __init__(self, default_sep: str = None):
        self.default_sep = default_sep or ic.def_sep

    def construct_from_node(
        self, call_node: ast.Call, evaluator: "VariableEvaluator" = None
    ) -> tuple[str, dict]:
        sep = next(
            (
                kw.value.value
                for kw in call_node.keywords
                if kw.arg == "sep" and isinstance(kw.value, ast.Constant)
            ),
            self.default_sep,
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
                    wrapper = f'{ic.i18n_function_name[0]}(f"{{{expr_src}}}")'
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
                if evaluator:
                    variables[expr_] = evaluator.evaluate(expr, conversion, format_spec)
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
                return FormatError(e)
        except Exception as e:
            return EvaluateError(e)

    def _evaluate_basic(self, expr: str) -> any:
        """基础求值"""
        if expr.isidentifier():
            # 简单变量查找
            return self.locals.get(expr, self.globals.get(expr, None))
        else:
            # 复杂表达式求值
            compiled_expr = compile(expr, "<string>", "eval")
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
    """
    通过组合 ASTWalker、StringConstructor 和 VariableEvaluator，对指定的 AST 节点进行解析。
    """

    @staticmethod
    def get_code_block(frame: FrameType):
        """
        获取调用位置的代码块
        :param frame:
        :return:
        """
        positions = inspect.getframeinfo(frame).positions
        filename = frame.f_code.co_filename
        lines = linecache.getlines(filename)

        start_line = positions.lineno - 1
        end_line = positions.end_lineno - 1
        # 如果是单行
        if start_line == end_line:
            return (
                lines[start_line]
                .encode()[positions.col_offset : positions.end_col_offset]
                .decode()
            )

        # 如果是多行

        # 处理第一行
        result = [lines[start_line].encode()[positions.col_offset :].decode()]

        # 处理中间行
        for i in range(start_line + 1, end_line):
            result.append(lines[i])

        # 处理最后一行
        result.append(lines[end_line].encode()[: positions.end_col_offset].decode())
        return "".join(result)

    def extract_all_strings(self, *, node: ast.AST) -> list[str]:
        """
        仅提取解析后的字符串，默认只解析第一个匹配的调用节点。
        """
        target_nodes = ASTWalker.get_target_nodes(node)

        if not target_nodes:
            return []
        strings, _ = self._extract(
            target_nodes=target_nodes,
            sep=ic.def_sep,
        )
        return strings

    def extract_string_data(
        self,
        *,
        sep: str = None,
        frame: FrameType = None,
        call_nodes: list[ast.Call] = None,
    ) -> StringData | None:
        """
        解析第一个匹配的调用节点，并返回构造后的字符串及变量数据。
        """
        # 节点解析的性能开销大, 尽量使用缓存
        if call_nodes:
            target_nodes = call_nodes
        else:
            call_text = self.get_code_block(frame)
            node = ast.parse(call_text.strip())
            target_nodes = ASTWalker.get_target_nodes(node)

        if not target_nodes:
            return None

        strings, variables_collected = self._extract(
            target_nodes=target_nodes[:1],
            sep=sep,
            get_variables_value=True,
            frame=frame,
        )
        return StringData(strings[0], variables_collected, target_nodes[:1])

    @staticmethod
    def _extract(
        *,
        target_nodes: list[ast.Call],
        sep: str | None = None,
        get_variables_value: bool = False,
        frame: FrameType = None,
    ) -> tuple[list[str], dict]:
        variables_collected: dict = {}

        evaluator: VariableEvaluator | None = None
        if get_variables_value and frame:
            evaluator = VariableEvaluator(frame.f_globals, frame.f_locals)

        string_constructor = StringConstructor(sep or ic.i18n_function_name)
        strings_set = set()

        for call_node in target_nodes:
            constructed, vars_found = string_constructor.construct_from_node(
                call_node, evaluator
            )
            strings_set.add(constructed)
            variables_collected.update(vars_found)
        return list(strings_set), variables_collected
