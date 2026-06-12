"""Unit tests for function span extraction."""

import pytest

from black_box_unlock.spans import FunctionSpan, indentation_spans, python_spans, span_at

SRC = """\
import os


@decorator
def top(a):
    return a


class Box:
    def method(self):
        def inner():
            return 1
        return inner


async def fetch():
    return 2
"""


class TestPythonSpans:
    def test_decorated_function_span_starts_at_decorator(self):
        spans = {s.name: s for s in python_spans(SRC)}
        assert spans["top"].start == 4  # @decorator line
        assert spans["top"].end == 6

    def test_method_gets_qualified_name(self):
        names = {s.name for s in python_spans(SRC)}
        assert "Box.method" in names

    def test_nested_function_qualified(self):
        names = {s.name for s in python_spans(SRC)}
        assert "Box.method.inner" in names

    def test_async_def_included(self):
        names = {s.name for s in python_spans(SRC)}
        assert "fetch" in names

    def test_syntax_error_raises(self):
        with pytest.raises(SyntaxError):
            python_spans("def broken(:\n")


class TestSpanAt:
    def test_innermost_span_wins(self):
        spans = python_spans(SRC)
        hit = span_at(spans, 11)  # inside inner()
        assert hit is not None and hit.name == "Box.method.inner"

    def test_line_outside_all_spans_returns_none(self):
        assert span_at(python_spans(SRC), 1) is None  # import line


class TestIndentationSpans:
    def test_finds_defs_with_block_extent(self):
        spans = {s.name: s for s in indentation_spans(SRC)}
        assert spans["top"].start == 5  # def line (no decorator awareness in fallback)
        assert spans["top"].end == 6
        assert "method" in spans  # unqualified in fallback

    def test_works_on_python2_print(self):
        src = "def f():\n    print 'hi'\n"
        spans = indentation_spans(src)
        assert spans[0] == FunctionSpan("f", 1, 2)
