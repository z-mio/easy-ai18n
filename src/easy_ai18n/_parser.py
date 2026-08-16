"""
AST parser.

Extracts the source code block of a translation function call,
parses it into an AST, traverses the AST to locate the call node,
and extracts the string and f-string variables.

Everything that depends only on the call site's source text is
compiled once into an immutable ``_CompiledCall``; each invocation
then only evaluates the precompiled expressions against the caller's
frame. The call span comes straight from the code object's
``co_positions()`` (no ``inspect.getframeinfo``), the source file is
cached per ``(filename, mtime, size)``, and non-string arguments are
wrapped by constructing the f-string AST node directly (no
source-text round trip).
"""

from __future__ import annotations

import ast
import itertools
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from types import CodeType, FrameType
from typing import Any

from ._types import Text
from .errors import EvaluationError, FormatError, UnsupportedSyntaxError

_CONVERSIONS = {97: "a", 114: "r", 115: "s"}

_FILE_CACHE_MAX = 512
"""How many source files the byte-line cache may hold.

Each entry is one file's full bytes, so this caps memory at roughly
``512 × Average file size`` (≈ 2.5–25 MB for typical 5–50 KB files). It is
generous enough for the files a running app actually parses; a cache
miss only re-reads one file, so undersizing costs a little time and
never correctness.
"""


@dataclass(frozen=True, slots=True, kw_only=True)
class _CompiledSpec:
    """A format spec: a concrete string, or a template with nested exprs."""

    concrete: str | None
    template: str | None
    exprs: tuple[_CompiledExpr, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class _CompiledExpr:
    """One f-string expression: placeholder text plus precompiled code."""

    placeholder: str
    source: str
    code: CodeType | None  # None when compiled for the build path
    conversion: str | None
    spec: _CompiledSpec | None


@dataclass(frozen=True, slots=True, kw_only=True)
class _CompiledCall:
    """The static part of one translation call site."""

    sep: str
    raw_parts: tuple[str, ...]
    exprs: tuple[_CompiledExpr, ...]


@dataclass(kw_only=True)
class StringData:
    string: Text
    variables: dict[str, object]
    compiled: _CompiledCall


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
        # 前置选择器: _[]() 或 obj._[]() —— 把 slice 提升为被调函数
        elif isinstance(func, ast.Subscript) and (
            (isinstance(func.value, ast.Name) and func.value.id in self.func_names)
            or (isinstance(func.value, ast.Attribute) and func.value.attr in self.func_names)
        ):
            new_call = ast.Call(func=func.slice, args=node.args, keywords=node.keywords)
            self.nodes.append(ast.copy_location(new_call, node))
        # 深入其他可能的子节点
        self.generic_visit(node)


class UnsupportedSyntaxValidator:
    def __init__(self, source_path: Path | None = None, source: str | None = None):
        self.source_path = source_path
        self.source_lines = source.splitlines() if source else []

    def validate_call(self, call_node: ast.Call) -> None:
        # 一次遍历覆盖全部参数与关键字值(与原来逐个 ast.walk 语义一致);
        # 用 Tuple 包一层是为了不遍历 func(如 async 代码中合法的 _[await x](...))
        combined = ast.Tuple(elts=[*call_node.args, *(kw.value for kw in call_node.keywords)], ctx=ast.Load())
        for node in ast.walk(combined):
            if not isinstance(node, ast.JoinedStr):
                continue
            for value in node.values:
                if not isinstance(value, ast.FormattedValue):
                    continue
                if any(isinstance(child, ast.Await) for child in ast.walk(value.value)):
                    self._raise_unsupported(value.value)

    def _raise_unsupported(self, node: ast.AST) -> None:
        location = self._location(node)
        message = (
            f"Build failed: await not allowed inside f-string {location}"
            f"\nExecute await first, then pass the result into the f-string."
        )
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


# ── 静态编译 ────────────────────────────────────────────────────


def _make_placeholder(source: str, conversion: str | None, spec: _CompiledSpec | None) -> str:
    """Rebuild the placeholder token ``{expr!c:spec}`` of a formatted value."""
    spec_str = None if spec is None else (spec.concrete if spec.concrete is not None else spec.template)
    return "{" + source + (f"!{conversion}" if conversion else "") + (f":{spec_str}" if spec_str else "") + "}"


def _compile_joined(values: list[ast.expr], *, compile_code: bool) -> tuple[str, tuple[_CompiledExpr, ...]]:
    """Compile the values of a ``JoinedStr`` into text plus compiled expressions."""
    parts: list[str] = []
    exprs: list[_CompiledExpr] = []
    for value in values:
        if isinstance(value, ast.Constant):
            parts.append(str(value.value))
        elif isinstance(value, ast.FormattedValue):
            source = ast.unparse(value.value)
            conversion = _CONVERSIONS.get(value.conversion)
            spec = _compile_spec(value.format_spec, compile_code=compile_code)
            placeholder = _make_placeholder(source, conversion, spec)
            parts.append(placeholder)
            exprs.append(
                _CompiledExpr(
                    placeholder=placeholder,
                    source=source,
                    code=compile(source, "<string>", "eval") if compile_code else None,
                    conversion=conversion,
                    spec=spec,
                )
            )
    return "".join(parts), tuple(exprs)


def _compile_spec(spec_node: ast.expr | None, *, compile_code: bool) -> _CompiledSpec | None:
    """Compile a format spec: concrete string, template, or None when unsupported."""
    if spec_node is None:
        return None
    if isinstance(spec_node, ast.Constant):
        return _CompiledSpec(concrete=str(spec_node.value), template=None, exprs=())
    if not isinstance(spec_node, ast.JoinedStr):
        return None
    template, exprs = _compile_joined(spec_node.values, compile_code=compile_code)
    return _CompiledSpec(concrete=None, template=template, exprs=exprs)


def _compile_call(call_node: ast.Call, default_sep: str, *, compile_code: bool) -> _CompiledCall:
    """Compile the static part of one translation call site."""
    sep = default_sep
    for kw in call_node.keywords:
        if kw.arg == "sep" and isinstance(kw.value, ast.Constant):
            sep = str(kw.value.value)
            break

    raw_parts: list[str] = []
    exprs: list[_CompiledExpr] = []
    for arg in call_node.args:
        if isinstance(arg, ast.Constant):
            # 常量字符串直接添加
            raw_parts.append(str(arg.value))
            continue
        if not isinstance(arg, ast.JoinedStr):
            # 直接构造等价的 f-string 节点, 避免 "unparse → 拼字符串 → 重新 parse" 的往返
            arg = ast.JoinedStr(values=[ast.FormattedValue(value=arg, conversion=-1, format_spec=None)])
        # 单个参数内部以空串拼接, 参数之间才用 sep 连接
        part, found = _compile_joined(arg.values, compile_code=compile_code)
        raw_parts.append(part)
        exprs.extend(found)
    return _CompiledCall(sep=sep, raw_parts=tuple(raw_parts), exprs=tuple(exprs))


# ── 动态求值 ────────────────────────────────────────────────────


def _apply_conversion(value: object, conversion: str) -> object:
    """Apply a conversion flag (``!s``, ``!r``, ``!a``) to a value."""
    if conversion == "s":
        return str(value)
    if conversion == "r":
        return repr(value)
    if conversion == "a":
        return ascii(value)
    return value


def _resolve_spec(spec: _CompiledSpec, globals_dict: dict[str, Any], locals_dict: dict[str, Any]) -> str:
    """Resolve a format spec template to a concrete spec string."""
    if spec.concrete is not None:
        return spec.concrete
    resolved = spec.template or ""
    for nested in spec.exprs:
        resolved = resolved.replace(nested.placeholder, str(_evaluate_raw(nested, globals_dict, locals_dict)))
    return resolved


def _evaluate_raw(expr: _CompiledExpr, globals_dict: dict[str, Any], locals_dict: dict[str, Any]) -> object:
    """Evaluate without error wrapping (used inside format specs)."""
    if expr.code is None:
        raise RuntimeError(f"expression {expr.source!r} was not compiled")
    value = eval(expr.code, globals_dict, locals_dict)
    if expr.conversion:
        value = _apply_conversion(value, expr.conversion)
    if expr.spec is not None:
        value = format(value, _resolve_spec(expr.spec, globals_dict, locals_dict))
    return value


def _evaluate_expr(expr: _CompiledExpr, globals_dict: dict[str, Any], locals_dict: dict[str, Any]) -> object:
    """Evaluate one expression, mirroring the original error layering."""
    if expr.code is None:
        raise EvaluationError(f"expression {expr.source!r} was not compiled")
    try:
        value = eval(expr.code, globals_dict, locals_dict)
        if expr.conversion:
            value = _apply_conversion(value, expr.conversion)
    except Exception as e:
        raise EvaluationError(str(e)) from e
    if expr.spec is None:
        return value
    try:
        return format(value, _resolve_spec(expr.spec, globals_dict, locals_dict))
    except Exception as e:
        raise FormatError(str(e)) from e


def evaluate_call(
    compiled: _CompiledCall,
    globals_dict: dict[str, Any],
    locals_dict: dict[str, Any],
) -> dict[str, object]:
    """Evaluate the dynamic part of a compiled call: placeholder -> value."""
    variables: dict[str, object] = {}
    for expr in compiled.exprs:
        variables[expr.placeholder] = _evaluate_expr(expr, globals_dict, locals_dict)
    return variables


class ASTParser:
    def __init__(self, sep: str, func_names: list[str]):
        self.sep = sep
        self.func_names = func_names

    @staticmethod
    @lru_cache(maxsize=_FILE_CACHE_MAX)
    def _read_file_lines(filename: str, _mtime_ns: int, _size: int) -> tuple[bytes, ...]:
        """Read a source file's byte lines.

        ``_mtime_ns`` and ``_size`` never appear in the body: ``lru_cache``
        keys on every argument, so they exist purely as the invalidation
        key. An edited file has a new ``(mtime, size)`` pair and forces a
        re-read instead of reusing stale lines; keeping only ``filename``
        would cache the first version forever.
        """
        with open(filename, "rb") as f:
            return tuple(f.read().splitlines(keepends=True))

    @staticmethod
    def _call_span(frame: FrameType) -> tuple[int, int, int, int] | None:
        """The source span of the CALL instruction, straight from the code object.

        Returns ``(lineno, end_lineno, col_offset, end_col_offset)`` (1-based
        lines, byte-based columns), or ``None`` when unavailable.
        """
        if frame.f_lasti < 0:
            return None
        try:
            pos = next(itertools.islice(frame.f_code.co_positions(), frame.f_lasti // 2, None))
        except (StopIteration, ValueError):
            return None
        lineno, end_lineno, col_offset, end_col_offset = pos
        if lineno is None or end_lineno is None or col_offset is None or end_col_offset is None:
            return None
        return lineno, end_lineno, col_offset, end_col_offset

    def get_code_block(self, frame: FrameType) -> str:
        """The exact source text of the call, or ``""`` when unavailable."""
        span = self._call_span(frame)
        if span is None:
            return ""
        lineno, end_lineno, col_offset, end_col_offset = span
        filename = frame.f_code.co_filename
        try:
            st = os.stat(filename)
        except OSError:
            return ""
        lines = self._read_file_lines(filename, st.st_mtime_ns, st.st_size)
        start, end = lineno - 1, end_lineno - 1
        if start >= len(lines) or end >= len(lines):
            return ""
        try:
            if start == end:
                return lines[start][col_offset:end_col_offset].decode("utf-8")
            parts = [lines[start][col_offset:]]
            parts.extend(lines[start + 1 : end])
            parts.append(lines[end][:end_col_offset])
            return "".join(segment.decode("utf-8") for segment in parts)
        except UnicodeDecodeError:
            return ""

    def compile_from_frame(self, frame: FrameType) -> _CompiledCall | None:
        """Compile the translation call at the given frame, or None when unavailable."""
        call_text = self.get_code_block(frame)
        if not call_text:
            return None
        node = ast.parse(call_text.strip())
        target_nodes = self.get_target_nodes(node)
        if not target_nodes:
            return None
        return _compile_call(target_nodes[0], self.sep, compile_code=True)

    @staticmethod
    def evaluate(compiled: _CompiledCall, frame: FrameType) -> StringData:
        """Evaluate a compiled call against the frame's namespace."""
        variables = evaluate_call(compiled, frame.f_globals, frame.f_locals)
        template = compiled.sep.join(compiled.raw_parts)
        return StringData(string=Text(template) if template else Text(""), variables=variables, compiled=compiled)

    def extract_all(
        self,
        *,
        node: ast.AST,
        source_path: Path | None = None,
        source: str | None = None,
    ) -> list[StringData]:
        """Extract all translation strings from an AST node.

        Args:
            node: The AST node to search.
            source_path: The source file path (for error reporting).
            source: The source code (for error reporting).

        Returns:
            A list of ``StringData`` objects for each matched call.
        """
        target_nodes = self.get_target_nodes(node)
        if not target_nodes:
            return []

        results: list[StringData] = []
        validator = UnsupportedSyntaxValidator(source_path, source)
        for call_node in target_nodes:
            validator.validate_call(call_node)
            compiled = _compile_call(call_node, self.sep, compile_code=False)
            template = compiled.sep.join(compiled.raw_parts)
            variables: dict[str, object] = {expr.placeholder: None for expr in compiled.exprs}
            results.append(
                StringData(
                    string=Text(template) if template else Text(""),
                    variables=variables,
                    compiled=compiled,
                )
            )
        return results

    def get_target_nodes(self, node: ast.AST) -> list[ast.Call]:
        visitor = CallVisitor(self.func_names)
        visitor.visit(node)
        return visitor.nodes
