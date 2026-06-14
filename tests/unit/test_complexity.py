"""Unit tests for indentation-based complexity."""

import json

from black_box_unlock.complexity import indentation_complexity, indentation_complexity_lines


class TestIndentationComplexityLines:
    def test_sums_indentation_levels(self):
        lines = ["def f():", "    if x:", "        return 1", "    return 0"]
        assert indentation_complexity_lines(lines) == 4.0

    def test_blank_lines_ignored(self):
        assert indentation_complexity_lines(["    a = 1", "", "   "]) == 1.0

    def test_tabs_expand(self):
        assert indentation_complexity_lines(["\tx = 1"]) == 1.0


class TestIndentationComplexity:
    def test_flat_file_has_zero_complexity(self, tmp_path):
        f = tmp_path / "flat.py"
        f.write_text("a = 1\nb = 2\n")

        assert indentation_complexity(f) == 0.0

    def test_sums_indentation_levels(self, tmp_path):
        f = tmp_path / "nested.py"
        f.write_text(
            "def f():\n"  # 0 levels
            "    if x:\n"  # 1 level
            "        return 1\n"  # 2 levels
        )

        assert indentation_complexity(f) == 3.0

    def test_tabs_count_as_one_level(self, tmp_path):
        f = tmp_path / "tabs.py"
        f.write_text("def f():\n\treturn 1\n")

        assert indentation_complexity(f) == 1.0

    def test_blank_lines_ignored(self, tmp_path):
        f = tmp_path / "blanks.py"
        f.write_text("def f():\n\n    return 1\n")

        assert indentation_complexity(f) == 1.0

    def test_missing_file_is_zero(self, tmp_path):
        assert indentation_complexity(tmp_path / "gone.py") == 0.0

    def test_binary_content_is_zero(self, tmp_path):
        f = tmp_path / "blob.bin"
        f.write_bytes(b"\x00\x01" + b" " * 64 + b"\n" + b"\x00" * 32)

        assert indentation_complexity(f) == 0.0


class TestDataAndGeneratedFilesScoreZero:
    """Data/serialized/generated files inflate indentation complexity by sheer
    size without representing code complexity, so they must not become hotspots."""

    def test_json_data_is_zero(self, tmp_path):
        f = tmp_path / "seeds.json"
        f.write_text('{\n    "a": {\n        "b": 1\n    }\n}\n')  # deeply indented data
        assert indentation_complexity(f) == 0.0

    def test_yaml_config_still_scores(self, tmp_path):
        # config/markup is a legitimate maintenance hotspot - a churning k8s/CI/
        # spec YAML should stay visible, not be silenced like serialized data.
        f = tmp_path / "deployment.yaml"
        f.write_text("spec:\n  template:\n    containers:\n      - name: x\n")
        assert indentation_complexity(f) > 0.0

    def test_lockfile_is_zero(self, tmp_path):
        f = tmp_path / "yarn.lock"
        f.write_text("dep@1:\n  version 1\n    sub: x\n")
        assert indentation_complexity(f) == 0.0

    def test_package_lock_json_is_zero(self, tmp_path):
        f = tmp_path / "package-lock.json"
        f.write_text('{\n    "x": {\n        "y": 1\n    }\n}\n')
        assert indentation_complexity(f) == 0.0

    def test_minified_asset_is_zero(self, tmp_path):
        f = tmp_path / "bundle.min.js"
        f.write_text("    var a=1;\n        var b=2;\n")
        assert indentation_complexity(f) == 0.0

    def test_real_code_extension_still_scores(self, tmp_path):
        # guard must be extension-scoped, not zero everything
        f = tmp_path / "service.rb"
        f.write_text("def f\n  if x\n    g\n  end\nend\n")
        assert indentation_complexity(f) > 0.0


def _write_ipynb(path, cells):
    """Write a minimal .ipynb with the given cell list."""
    nb = {"cells": cells, "metadata": {}, "nbformat": 4, "nbformat_minor": 5}
    path.write_text(json.dumps(nb, indent=4))


class TestNotebookComplexity:
    def test_flat_code_cell_with_deep_json_envelope_scores_low(self, tmp_path):
        f = tmp_path / "flat.ipynb"
        _write_ipynb(f, [{"cell_type": "code", "source": ["x = 1\n", "y = 2\n"]}])
        assert indentation_complexity(f) == 0.0

    def test_nested_code_cell_scores_cell_complexity(self, tmp_path):
        f = tmp_path / "nested.ipynb"
        source = ["def f():\n", "    if x:\n", "        return 1\n"]
        _write_ipynb(f, [{"cell_type": "code", "source": source}])
        expected = indentation_complexity_lines(["def f():", "    if x:", "        return 1"])
        assert indentation_complexity(f) == expected

    def test_markdown_only_notebook_scores_zero(self, tmp_path):
        f = tmp_path / "docs.ipynb"
        _write_ipynb(f, [{"cell_type": "markdown", "source": ["# Title\n", "  body\n"]}])
        assert indentation_complexity(f) == 0.0

    def test_malformed_ipynb_scores_zero(self, tmp_path):
        f = tmp_path / "broken.ipynb"
        f.write_text("not json {{{")
        assert indentation_complexity(f) == 0.0

    def test_source_as_single_string(self, tmp_path):
        f = tmp_path / "str_source.ipynb"
        _write_ipynb(f, [{"cell_type": "code", "source": "    x = 1\n"}])
        assert indentation_complexity(f) == 1.0


class TestGeneratedFileComplexity:
    def test_protoc_generated_py_scores_zero(self, tmp_path):
        f = tmp_path / "proto_pb2.py"
        f.write_text("# Code generated by protoc. DO NOT EDIT.\ndef f():\n    return 1\n")
        assert indentation_complexity(f) == 0.0

    def test_rails_schema_scores_zero(self, tmp_path):
        f = tmp_path / "schema.rb"
        body = (
            "# This file is auto-generated from the current state of the database.\n"
            "# DO NOT EDIT.\n"
            "def f\n  x\nend\n"
        )
        f.write_text(body)
        assert indentation_complexity(f) == 0.0

    def test_handwritten_py_still_scores(self, tmp_path):
        f = tmp_path / "logic.py"
        f.write_text("def f():\n    if x:\n        return 1\n")
        assert indentation_complexity(f) > 0.0
