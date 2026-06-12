"""Function span extraction: exact via ast, indentation heuristic as fallback."""

import ast
import re
from dataclasses import dataclass

_DEF_RE = re.compile(r"^(\s*)(?:async\s+)?def\s+(\w+)")
_TAB_SIZE = 4


@dataclass(frozen=True)
class FunctionSpan:
    """A function's extent in a source file (1-based, inclusive)."""

    name: str  # qualified: "Class.method", "outer.inner", or "func"
    start: int  # decorator-aware in the ast path
    end: int


def python_spans(source: str) -> list[FunctionSpan]:
    """Extract exact function spans via ast.

    Raises:
        SyntaxError: If the source does not parse (e.g. Python 2).
    """
    tree = ast.parse(source)
    spans: list[FunctionSpan] = []

    def visit(node: ast.AST, prefix: str) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef):
                start = child.decorator_list[0].lineno if child.decorator_list else child.lineno
                spans.append(
                    FunctionSpan(f"{prefix}{child.name}", start, child.end_lineno or start)
                )
                visit(child, f"{prefix}{child.name}.")
            elif isinstance(child, ast.ClassDef):
                visit(child, f"{prefix}{child.name}.")
            else:
                visit(child, prefix)

    visit(tree, "")
    return spans


def indentation_spans(source: str) -> list[FunctionSpan]:
    """Detect def boundaries heuristically for source that ast cannot parse.

    Span = def line through the last non-blank line more indented than the def.
    Names are unqualified; decorators are not included in the span.
    """
    lines = source.splitlines()
    spans: list[FunctionSpan] = []
    for i, line in enumerate(lines, 1):
        m = _DEF_RE.match(line)
        if not m:
            continue
        def_indent = _indent_width(line)
        end = i
        for j in range(i + 1, len(lines) + 1):
            text = lines[j - 1]
            if not text.strip():
                continue
            if _indent_width(text) <= def_indent:
                break
            end = j
        spans.append(FunctionSpan(m.group(2), i, end))
    return spans


def span_at(spans: list[FunctionSpan], line: int) -> FunctionSpan | None:
    """Return the innermost span containing the line, or None."""
    best: FunctionSpan | None = None
    for s in spans:
        if s.start <= line <= s.end and (best is None or s.end - s.start < best.end - best.start):
            best = s
    return best


def _indent_width(line: str) -> int:
    expanded = line.expandtabs(_TAB_SIZE)
    return len(expanded) - len(expanded.lstrip(" "))
