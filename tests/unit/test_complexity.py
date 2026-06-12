"""Unit tests for indentation-based complexity."""

from black_box_unlock.complexity import indentation_complexity


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
