"""Unit tests for X-Ray patch parsing and attribution."""

from black_box_unlock.git.xray import (
    DIFF_DRIVERS,
    Hunk,
    _attribute_hunk,
    _attributes_content,
    _header_name,
    parse_patch_log,
)
from black_box_unlock.spans import FunctionSpan

PATCH = (
    "\x01aaa111\n"
    "diff --git a/mod.py b/mod.py\n"
    "index 111..222 100644\n"
    "--- a/mod.py\n"
    "+++ b/mod.py\n"
    "@@ -5,2 +5,3 @@ def alpha(a, b):\n"
    "+    x = 1\n"
    "@@ -20 +21,0 @@ def beta():\n"
    "-    gone = 1\n"
    "\x01bbb222\n"
    "diff --git a/mod.py b/mod.py\n"
    "Binary files a/mod.py and b/mod.py differ\n"
)


class TestParsePatchLog:
    def test_parses_commits_and_hunks(self):
        commits = parse_patch_log(PATCH)
        assert len(commits) == 1  # binary-only commit dropped
        assert commits[0].sha == "aaa111"
        assert commits[0].hunks[0] == Hunk(5, 2, 5, 3, "def alpha(a, b):")

    def test_omitted_count_defaults_to_one(self):
        commits = parse_patch_log("\x01c1\n@@ -5 +7 @@ def f():\n")
        h = commits[0].hunks[0]
        assert (h.old_count, h.new_count) == (1, 1)

    def test_deletion_hunk_zero_new_count(self):
        commits = parse_patch_log(PATCH)
        h = commits[0].hunks[1]
        assert h.new_count == 0 and h.old_count == 1


class TestAttributeHunk:
    SPANS = [FunctionSpan("alpha", 1, 10), FunctionSpan("beta", 12, 20)]

    def test_added_lines_apportioned_per_line(self):
        # hunk spans the gap: lines 9-13 -> 2 lines alpha, 2 lines beta, line 11 unowned;
        # all 5 deleted lines go to the probe span (line 9 -> alpha)
        hunk = Hunk(9, 5, 9, 5, "")
        out = _attribute_hunk(hunk, self.SPANS)
        assert out == {"alpha": [2, 5], "beta": [2, 0]}

    def test_deletion_only_hunk_attributed_to_probe_span(self):
        hunk = Hunk(15, 3, 14, 0, "")
        out = _attribute_hunk(hunk, self.SPANS)
        assert out == {"beta": [0, 3]}

    def test_no_spans_falls_back_to_header(self):
        hunk = Hunk(5, 1, 5, 2, "def alpha(a, b):")
        assert _attribute_hunk(hunk, []) == {"alpha": [2, 1]}

    def test_line_outside_spans_dropped(self):
        hunk = Hunk(11, 0, 11, 1, "")
        assert _attribute_hunk(hunk, self.SPANS) == {}


class TestHeaderName:
    def test_extracts_python_def_name(self):
        header = "def fetch_git_history(repo_path: Path) -> dict:"
        assert _header_name(header) == "fetch_git_history"

    def test_non_python_header_kept_trimmed(self):
        header = "func (s *Server) Handle(w http.ResponseWriter) {"
        assert _header_name(header) == header

    def test_empty_header_is_none(self):
        assert _header_name("") is None


class TestAttributesContent:
    def test_maps_python_and_go(self):
        content = _attributes_content()
        assert "*.py diff=python" in content
        assert "*.go diff=golang" in content
        assert DIFF_DRIVERS[".py"] == "python"


class TestFunctionCouplingPairs:
    TOUCHED = {
        "alpha": {"c1", "c2", "c3", "c4"},
        "beta": {"c1", "c2", "c3"},
        "gamma": {"c4"},
        "vanished": {"c1", "c2"},
    }

    def test_pair_with_shared_revisions_and_ratio(self):
        from black_box_unlock.git.xray import _function_coupling

        pairs = _function_coupling(self.TOUCHED, {"alpha", "beta", "gamma"}, min_ratio=0.3)
        assert len(pairs) == 1
        p = pairs[0]
        assert (p.function_a, p.function_b) == ("alpha", "beta")
        assert p.shared_revisions == 3
        assert p.coupling_ratio == 1.0  # 3 / min(4, 3)

    def test_single_shared_revision_filtered(self):
        from black_box_unlock.git.xray import _function_coupling

        # alpha & gamma share only c4 -> below the floor of 2
        pairs = _function_coupling(self.TOUCHED, {"alpha", "gamma"}, min_ratio=0.0)
        assert pairs == []

    def test_threshold_filters_low_ratios(self):
        from black_box_unlock.git.xray import _function_coupling

        touched = {"a": {f"c{i}" for i in range(10)}, "b": {"c0", "c1", "c99x", "c98x"}}
        # shared=2, min revs=4 -> ratio 0.5
        assert _function_coupling(touched, {"a", "b"}, min_ratio=0.6) == []
        assert len(_function_coupling(touched, {"a", "b"}, min_ratio=0.5)) == 1

    def test_universe_restriction_excludes_vanished(self):
        from black_box_unlock.git.xray import _function_coupling

        # vanished shares 2 commits with alpha and beta but is not in the universe
        pairs = _function_coupling(self.TOUCHED, {"alpha", "beta"}, min_ratio=0.3)
        names = {p.function_a for p in pairs} | {p.function_b for p in pairs}
        assert "vanished" not in names

    def test_deterministic_order(self):
        from black_box_unlock.git.xray import _function_coupling

        touched = {
            "a": {"c1", "c2"},
            "b": {"c1", "c2"},
            "x": {"c3", "c4"},
            "y": {"c3", "c4"},
        }
        pairs = _function_coupling(touched, {"a", "b", "x", "y"}, min_ratio=0.3)
        assert [(p.function_a, p.function_b) for p in pairs] == [("a", "b"), ("x", "y")]
