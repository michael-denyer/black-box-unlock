# Function X-Ray Implementation Plan (BBU-6351)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Per-function churn and hotspot scoring (Tornhill's X-Ray): auto-embedded for top-N hotspots in `analyze-repo`, on demand via `bbu xray FILE` and a seventh MCP tool `xray_file`.

**Architecture:** One git pass per file (`git log -p -U0` with injected diff drivers) parsed into per-commit hunks; for `.py` files each revision's content is fetched (`git show`, capped 200) and hunks are attributed to exact `ast` spans (indentation fallback on SyntaxError); other languages use the hunk-header function name. Spec: `.planning/superpowers/specs/2026-06-12-function-xray-design.md`.

**Tech Stack:** Python 3.10+ stdlib only (ast, re, subprocess, tempfile), pydantic, typer, pytest. No new dependencies.

---

### Task 1: complexity.py line-slice helper

**Files:**
- Modify: `src/black_box_unlock/complexity.py`
- Test: `tests/unit/test_complexity.py` (append)

- [ ] **Step 1: Write the failing test** (append to `tests/unit/test_complexity.py`)

```python
from black_box_unlock.complexity import indentation_complexity_lines


class TestIndentationComplexityLines:
    def test_sums_indentation_levels(self):
        lines = ["def f():", "    if x:", "        return 1", "    return 0"]
        assert indentation_complexity_lines(lines) == 4.0

    def test_blank_lines_ignored(self):
        assert indentation_complexity_lines(["    a = 1", "", "   "]) == 1.0

    def test_tabs_expand(self):
        assert indentation_complexity_lines(["\tx = 1"]) == 1.0
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/unit/test_complexity.py -v -p no:randomly --no-cov`
Expected: ImportError (`indentation_complexity_lines` not defined)

- [ ] **Step 3: Implement** — refactor `complexity.py` so the file-based function delegates:

```python
"""Indentation-based complexity proxy (Tornhill's whitespace method)."""

from collections.abc import Iterable
from pathlib import Path

TAB_SIZE = 4


def indentation_complexity_lines(lines: Iterable[str], tab_size: int = TAB_SIZE) -> float:
    """Sum of logical indentation levels across non-blank lines."""
    total = 0
    for line in lines:
        if not line.strip():
            continue
        expanded = line.expandtabs(tab_size)
        total += (len(expanded) - len(expanded.lstrip(" "))) // tab_size
    return float(total)


def indentation_complexity(file_path: Path, tab_size: int = TAB_SIZE) -> float:
    """Sum of logical indentation levels across non-blank lines of a file.

    Returns 0.0 for missing, unreadable, or binary files.
    """
    try:
        text = file_path.read_text(errors="ignore")
    except OSError:
        return 0.0
    if "\x00" in text:
        return 0.0
    return indentation_complexity_lines(text.splitlines(), tab_size)
```

(Keep the original docstring details if richer; behavior identical.)

- [ ] **Step 4: Run full complexity tests** — `uv run pytest tests/unit/test_complexity.py -v -p no:randomly --no-cov` → all PASS
- [ ] **Step 5: Commit** — `git add src/black_box_unlock/complexity.py tests/unit/test_complexity.py && git commit -m "refactor(complexity): extract line-slice helper for function spans"`

---

### Task 2: spans.py — function boundary extraction

**Files:**
- Create: `src/black_box_unlock/spans.py`
- Test: `tests/unit/test_spans.py`

- [ ] **Step 1: Write the failing tests**

```python
"""Unit tests for function span extraction."""

import pytest

from black_box_unlock.spans import FunctionSpan, indentation_spans, python_spans, span_at

SRC = '''\
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
'''


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
```

- [ ] **Step 2: Run to verify failure** — `uv run pytest tests/unit/test_spans.py -v -p no:randomly --no-cov` → ModuleNotFoundError

- [ ] **Step 3: Implement `src/black_box_unlock/spans.py`**

```python
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
    """Exact function spans via ast.

    Raises:
        SyntaxError: If the source does not parse (e.g. Python 2).
    """
    tree = ast.parse(source)
    spans: list[FunctionSpan] = []

    def visit(node: ast.AST, prefix: str) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
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
    """Heuristic def-boundary detection for source that ast cannot parse.

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
    """Innermost span containing the line, or None."""
    best: FunctionSpan | None = None
    for s in spans:
        if s.start <= line <= s.end and (best is None or s.end - s.start < best.end - best.start):
            best = s
    return best


def _indent_width(line: str) -> int:
    expanded = line.expandtabs(_TAB_SIZE)
    return len(expanded) - len(expanded.lstrip(" "))
```

- [ ] **Step 4: Run to verify pass** — same command → all PASS
- [ ] **Step 5: Commit** — `git add src/black_box_unlock/spans.py tests/unit/test_spans.py && git commit -m "feat(spans): ast function spans with indentation fallback"`

---

### Task 3: models — FunctionChurn, FileXRay, FileForensics.functions

**Files:**
- Modify: `src/black_box_unlock/core/models.py`
- Test: `tests/unit/core/test_models.py` (append)

- [ ] **Step 1: Write the failing tests** (append)

```python
from black_box_unlock.core.models import FileXRay, FunctionChurn


class TestFunctionChurn:
    def test_hotspot_score_is_revisions_times_complexity(self):
        f = FunctionChurn(
            name="f", start_line=1, end_line=5, revisions=3,
            lines_added=10, lines_deleted=2, complexity=4.0,
        )
        assert f.hotspot_score == 12.0

    def test_header_only_defaults(self):
        f = FunctionChurn(name="parse", revisions=2, lines_added=5, lines_deleted=1)
        assert f.start_line == 0 and f.end_line == 0
        assert f.complexity == 0.0 and f.hotspot_score == 0.0


class TestFileXRay:
    def test_serializes_with_computed_score(self):
        xr = FileXRay(
            path="a.py", days=365, revisions_analyzed=4, revision_cap_hit=False,
            functions=[FunctionChurn(name="f", revisions=1, lines_added=1, lines_deleted=0)],
        )
        dumped = xr.model_dump(mode="json")
        assert dumped["functions"][0]["hotspot_score"] == 0.0


class TestFileForensicsFunctions:
    def test_functions_default_empty(self):
        from black_box_unlock.core.models import FileForensics

        f = FileForensics(path="a.py", commits=1, lines_changed=1, authors=[], coupled_with=[])
        assert f.functions == []
```

- [ ] **Step 2: Run to verify failure** — `uv run pytest tests/unit/core/test_models.py -v -p no:randomly --no-cov` → ImportError

- [ ] **Step 3: Implement** — in `core/models.py`, above `FileForensics`:

```python
class FunctionChurn(BaseModel):
    """Per-function churn within one file (Tornhill's X-Ray)."""

    name: str
    start_line: int = 0  # 0 = boundaries unknown (header-only attribution)
    end_line: int = 0
    revisions: int
    lines_added: int
    lines_deleted: int
    complexity: float = 0.0

    @computed_field
    @property
    def hotspot_score(self) -> float:
        """Function hotspot score = revisions x complexity (file formula, function scale)."""
        return self.revisions * self.complexity


class FileXRay(BaseModel):
    """X-Ray result for one file."""

    path: str
    days: int
    revisions_analyzed: int
    revision_cap_hit: bool
    functions: list[FunctionChurn]
```

Add to `FileForensics`: `functions: list[FunctionChurn] = []` (after `bugfix_commits`).
Add to `AnalysisSummary`: `xrayed_files: int = 0`.

- [ ] **Step 4: Run model + full tests** — `uv run pytest tests/unit/core/test_models.py -v -p no:randomly --no-cov` then `uv run pytest -q` → all PASS
- [ ] **Step 5: Commit** — `git add src/black_box_unlock/core/models.py tests/unit/core/test_models.py && git commit -m "feat(models): FunctionChurn and FileXRay for function-level forensics"`

---

### Task 4: xray.py — patch-stream parser and hunk attribution

**Files:**
- Create: `src/black_box_unlock/git/xray.py`
- Test: `tests/unit/git/test_xray.py`

- [ ] **Step 1: Write the failing tests**

```python
"""Unit tests for X-Ray patch parsing and attribution."""

from black_box_unlock.git.xray import (
    DIFF_DRIVERS,
    CommitPatch,
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
        assert _header_name("def fetch_git_history(repo_path: Path) -> dict:") == "fetch_git_history"

    def test_non_python_header_kept_trimmed(self):
        assert _header_name("func (s *Server) Handle(w http.ResponseWriter) {") == (
            "func (s *Server) Handle(w http.ResponseWriter) {"
        )

    def test_empty_header_is_none(self):
        assert _header_name("") is None


class TestAttributesContent:
    def test_maps_python_and_go(self):
        content = _attributes_content()
        assert "*.py diff=python" in content
        assert "*.go diff=golang" in content
        assert DIFF_DRIVERS[".py"] == "python"
```

- [ ] **Step 2: Run to verify failure** — `uv run pytest tests/unit/git/test_xray.py -v -p no:randomly --no-cov` → ModuleNotFoundError

- [ ] **Step 3: Implement `src/black_box_unlock/git/xray.py`** (parser/attribution half)

```python
"""Per-function churn for one file via git patch parsing (Tornhill's X-Ray).

Engine: one `git log -p -U0` pass with git's built-in language diff drivers
injected via a temp core.attributesFile (an in-repo .gitattributes still wins).
For .py files, each revision's content is fetched and hunks are attributed to
exact ast spans (indentation fallback on SyntaxError); other languages use the
hunk-header function name, which git truncates at ~80 bytes.
"""

import re
import subprocess
import tempfile
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from ..complexity import indentation_complexity_lines
from ..core.exceptions import GitToolNotFoundError, NotAGitRepoError
from ..core.models import FileXRay, FunctionChurn
from ..spans import FunctionSpan, indentation_spans, python_spans, span_at

_COMMIT_MARKER = "\x01"
_PRETTY_FORMAT = f"{_COMMIT_MARKER}%H"
_HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@ ?(.*)$")
_HEADER_DEF_RE = re.compile(r"\bdef\s+(\w+)")

# Conservative map of extensions to git's built-in diff drivers (userdiff.c).
DIFF_DRIVERS = {
    ".py": "python", ".go": "golang", ".java": "java", ".kt": "kotlin",
    ".rs": "rust", ".rb": "ruby", ".php": "php", ".pl": "perl",
    ".cs": "csharp", ".c": "cpp", ".h": "cpp", ".cpp": "cpp", ".cc": "cpp",
    ".cxx": "cpp", ".hpp": "cpp", ".swift": "swift", ".ex": "elixir",
    ".exs": "elixir", ".dart": "dart", ".m": "objc", ".sh": "bash",
    ".bash": "bash", ".css": "css", ".html": "html", ".md": "markdown",
    ".tex": "tex", ".f90": "fortran", ".pas": "pascal", ".scm": "scheme",
}


@dataclass(frozen=True)
class Hunk:
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    header: str  # funcname text from the hunk header ("" if none)


@dataclass
class CommitPatch:
    sha: str
    hunks: list[Hunk] = field(default_factory=list)


def _attributes_content() -> str:
    """gitattributes content mapping known extensions to built-in diff drivers."""
    return "\n".join(f"*{ext} diff={drv}" for ext, drv in sorted(DIFF_DRIVERS.items())) + "\n"


def parse_patch_log(output: str) -> list[CommitPatch]:
    """Parse `git log -p -U0 --pretty=<marker>%H` output into commits with hunks.

    Commits without hunks (binary changes, merges without -m) are dropped.
    """
    commits: list[CommitPatch] = []
    current: CommitPatch | None = None
    for line in output.splitlines():
        if line.startswith(_COMMIT_MARKER):
            current = CommitPatch(sha=line[1:].strip())
            commits.append(current)
        elif current is not None:
            m = _HUNK_RE.match(line)
            if m:
                current.hunks.append(
                    Hunk(
                        old_start=int(m.group(1)),
                        old_count=int(m.group(2)) if m.group(2) is not None else 1,
                        new_start=int(m.group(3)),
                        new_count=int(m.group(4)) if m.group(4) is not None else 1,
                        header=m.group(5).strip(),
                    )
                )
    return [c for c in commits if c.hunks]


def _header_name(header: str) -> str | None:
    """Function identity from a hunk header: def name for Python, raw text otherwise."""
    if not header:
        return None
    m = _HEADER_DEF_RE.search(header)
    if m:
        return m.group(1)
    return header.strip() or None


def _attribute_hunk(hunk: Hunk, spans: list[FunctionSpan]) -> dict[str, list[int]]:
    """Map function name -> [added, deleted] for one hunk.

    With spans (Python): added lines are apportioned per post-image line to the
    innermost containing span; deletions go to the span containing the hunk's
    post-image position. Without spans: the hunk-header name takes everything.
    """
    out: dict[str, list[int]] = {}
    if not spans:
        name = _header_name(hunk.header)
        if name:
            out[name] = [hunk.new_count, hunk.old_count]
        return out
    for line in range(hunk.new_start, hunk.new_start + hunk.new_count):
        span = span_at(spans, line)
        if span:
            out.setdefault(span.name, [0, 0])[0] += 1
    if hunk.old_count:
        probe = max(hunk.new_start, 1)
        span = span_at(spans, probe)
        if span:
            out.setdefault(span.name, [0, 0])[1] += hunk.old_count
    return out
```

- [ ] **Step 4: Run to verify pass** — same command → all PASS
- [ ] **Step 5: Commit** — `git add src/black_box_unlock/git/xray.py tests/unit/git/test_xray.py && git commit -m "feat(xray): patch-stream parser and per-function hunk attribution"`

---

### Task 5: xray.py — git plumbing, aggregation, `xray_file()`

**Files:**
- Modify: `src/black_box_unlock/git/xray.py`
- Test: `tests/integration/test_xray.py`

- [ ] **Step 1: Write the failing integration tests** (real git, synthetic repo)

```python
"""Integration tests for xray_file against a real synthetic repository."""

import subprocess

import pytest

from black_box_unlock.core.exceptions import NotAGitRepoError
from black_box_unlock.git.xray import xray_file

ALPHA_V1 = "def alpha():\n    return 1\n\n\ndef beta():\n    return 2\n"
ALPHA_V2 = "def alpha():\n    x = 1\n    return x\n\n\ndef beta():\n    return 2\n"
ALPHA_V3 = "def alpha():\n    x = 2\n    return x\n\n\ndef beta():\n    return 2\n"
BETA_V2 = "def alpha():\n    x = 2\n    return x\n\n\ndef beta():\n    y = 5\n    return y\n"


def _run(args: list[str], cwd) -> None:
    subprocess.run(args, cwd=cwd, check=True, capture_output=True, text=True)


@pytest.fixture
def xray_repo(tmp_path):
    _run(["git", "init", "-b", "main"], tmp_path)
    _run(["git", "config", "user.email", "t@example.com"], tmp_path)
    _run(["git", "config", "user.name", "Tester"], tmp_path)
    mod = tmp_path / "mod.py"
    for i, content in enumerate([ALPHA_V1, ALPHA_V2, ALPHA_V3, BETA_V2]):
        mod.write_text(content)
        _run(["git", "add", "."], tmp_path)
        _run(["git", "commit", "-m", f"step {i}"], tmp_path)
    return tmp_path


class TestXrayFile:
    def test_per_function_revision_counts(self, xray_repo):
        result = xray_file(xray_repo, "mod.py", days=365)
        by_name = {f.name: f for f in result.functions}
        assert by_name["alpha"].revisions == 3  # creation + two edits
        assert by_name["beta"].revisions == 2  # creation + one edit

    def test_complexity_and_score_from_current_snapshot(self, xray_repo):
        result = xray_file(xray_repo, "mod.py", days=365)
        alpha = next(f for f in result.functions if f.name == "alpha")
        assert alpha.complexity == 2.0  # two indented lines in final alpha
        assert alpha.hotspot_score == 6.0
        assert alpha.start_line == 1 and alpha.end_line == 3

    def test_sorted_by_score_descending(self, xray_repo):
        result = xray_file(xray_repo, "mod.py", days=365)
        scores = [f.hotspot_score for f in result.functions]
        assert scores == sorted(scores, reverse=True)

    def test_revision_cap(self, xray_repo):
        result = xray_file(xray_repo, "mod.py", days=365, rev_cap=2)
        assert result.revisions_analyzed == 2
        assert result.revision_cap_hit is True

    def test_no_history_returns_empty(self, xray_repo):
        result = xray_file(xray_repo, "missing.py", days=365)
        assert result.functions == [] and result.revisions_analyzed == 0

    def test_not_a_repo_raises(self, tmp_path):
        with pytest.raises(NotAGitRepoError):
            xray_file(tmp_path / "nowhere", "mod.py")

    def test_vanished_function_excluded(self, xray_repo):
        mod = xray_repo / "mod.py"
        mod.write_text("def alpha():\n    x = 2\n    return x\n")  # beta deleted
        _run(["git", "add", "."], xray_repo)
        _run(["git", "commit", "-m", "drop beta"], xray_repo)
        result = xray_file(xray_repo, "mod.py", days=365)
        assert "beta" not in {f.name for f in result.functions}
```

- [ ] **Step 2: Run to verify failure** — `uv run pytest tests/integration/test_xray.py -v -p no:randomly --no-cov` → ImportError (`xray_file` not defined)

- [ ] **Step 3: Implement** — append to `src/black_box_unlock/git/xray.py`:

```python
def _git_patch_log(repo_path: Path, file_path: str, days: int) -> str:
    """One `git log -p -U0` pass for the file, with diff drivers injected."""
    attrs = tempfile.NamedTemporaryFile("w", suffix=".gitattributes", delete=False)
    attrs.write(_attributes_content())
    attrs.close()
    cmd = [
        "git",
        "-c", f"core.attributesFile={attrs.name}",
        "-c", "core.quotePath=false",
        "-C", str(repo_path),
        "log", f"--since={days} days ago",
        "--no-renames", "-p", "-U0",
        f"--pretty=format:{_PRETTY_FORMAT}",
        "--", file_path,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    except FileNotFoundError as e:
        raise GitToolNotFoundError("git not found on PATH") from e
    except subprocess.CalledProcessError as e:
        if e.returncode == 128 and (
            "does not have any commits" in e.stderr or "bad default revision" in e.stderr
        ):
            return ""
        raise
    finally:
        Path(attrs.name).unlink(missing_ok=True)
    return result.stdout


def _show(repo_path: Path, sha: str, file_path: str) -> str | None:
    """File content at a revision; None if absent there (e.g. deletion commit)."""
    result = subprocess.run(
        ["git", "-C", str(repo_path), "show", f"{sha}:{file_path}"],
        capture_output=True, text=True,
    )
    return result.stdout if result.returncode == 0 else None


def _spans_for(source: str) -> list[FunctionSpan]:
    try:
        return python_spans(source)
    except SyntaxError:
        return indentation_spans(source)


def xray_file(
    repo_path: Path, file_path: str, days: int = 365, rev_cap: int = 200
) -> FileXRay:
    """Per-function churn for one file (Tornhill's X-Ray).

    Ranks the file's functions by revisions x current indentation complexity.
    Python files get exact ast attribution per revision; other languages use
    git hunk-header names (complexity 0.0, ranked by revisions).

    Raises:
        NotAGitRepoError: If repo_path is not a git repository.
        GitToolNotFoundError: If the git binary is not installed.
    """
    if not (repo_path / ".git").exists():
        raise NotAGitRepoError(f"Not a git repository: {repo_path}")

    commits = parse_patch_log(_git_patch_log(repo_path, file_path, days))
    cap_hit = len(commits) > rev_cap
    commits = commits[:rev_cap]  # git log emits newest first
    is_python = file_path.endswith(".py")

    tallies: dict[str, list[int]] = defaultdict(lambda: [0, 0])  # name -> [added, deleted]
    touched: dict[str, set[str]] = defaultdict(set)  # name -> commit shas
    for commit in commits:
        spans: list[FunctionSpan] = []
        if is_python:
            content = _show(repo_path, commit.sha, file_path)
            if content is not None:
                spans = _spans_for(content)
        for hunk in commit.hunks:
            for name, (added, deleted) in _attribute_hunk(hunk, spans).items():
                tallies[name][0] += added
                tallies[name][1] += deleted
                touched[name].add(commit.sha)

    functions = _build_functions(repo_path, file_path, is_python, tallies, touched)
    functions.sort(key=lambda f: (-f.hotspot_score, -f.revisions, f.name))
    return FileXRay(
        path=file_path,
        days=days,
        revisions_analyzed=len(commits),
        revision_cap_hit=cap_hit,
        functions=functions,
    )


def _build_functions(
    repo_path: Path,
    file_path: str,
    is_python: bool,
    tallies: dict[str, list[int]],
    touched: dict[str, set[str]],
) -> list[FunctionChurn]:
    """Join churn tallies onto the current snapshot's spans (Python) or pass through."""
    if not is_python:
        return [
            FunctionChurn(
                name=name, revisions=len(touched[name]),
                lines_added=added, lines_deleted=deleted,
            )
            for name, (added, deleted) in tallies.items()
        ]
    full_path = repo_path / file_path
    if not full_path.exists():
        return []
    lines = full_path.read_text(errors="ignore").splitlines()
    current = {s.name: s for s in _spans_for("\n".join(lines))}
    functions: list[FunctionChurn] = []
    for name, (added, deleted) in tallies.items():
        span = current.get(name)
        if span is None:
            continue  # vanished within the window; ranking targets current code
        functions.append(
            FunctionChurn(
                name=name,
                start_line=span.start,
                end_line=span.end,
                revisions=len(touched[name]),
                lines_added=added,
                lines_deleted=deleted,
                complexity=indentation_complexity_lines(lines[span.start - 1 : span.end]),
            )
        )
    return functions
```

- [ ] **Step 4: Run to verify pass** — `uv run pytest tests/integration/test_xray.py tests/unit/git/test_xray.py -v -p no:randomly --no-cov` → all PASS
- [ ] **Step 5: Commit** — `git add src/black_box_unlock/git/xray.py tests/integration/test_xray.py && git commit -m "feat(xray): per-function churn engine with ast attribution"`

---

### Task 6: analyze-repo auto X-Ray (top N)

**Files:**
- Modify: `src/black_box_unlock/analysis.py` (`run_analysis` signature + after the files sort)
- Test: `tests/unit/test_analysis.py` (append)

- [ ] **Step 1: Write the failing tests** (append; follow the file's existing patch-style fixtures — it patches `fetch_git_history` etc.)

```python
class TestAutoXray:
    def _history(self):
        return {
            "entries": [
                {
                    "timestamp": "2026-06-01T10:00:00+00:00",
                    "author_email": "a@x.com",
                    "message": "feat: x",
                    "files": [{"path": "mod.py", "added_lines": 5, "deleted_lines": 0}],
                }
            ]
        }

    def test_top_files_get_functions(self, tmp_path):
        (tmp_path / "mod.py").write_text("def f():\n    return 1\n")
        (tmp_path / ".git").mkdir()
        from unittest.mock import patch

        from black_box_unlock.analysis import run_analysis
        from black_box_unlock.core.models import FileXRay, FunctionChurn

        fake = FileXRay(
            path="mod.py", days=30, revisions_analyzed=1, revision_cap_hit=False,
            functions=[FunctionChurn(name="f", revisions=1, lines_added=5, lines_deleted=0)],
        )
        with patch("black_box_unlock.analysis.fetch_git_history") as mock_hist:
            mock_hist.return_value = self._history()
            with patch("black_box_unlock.analysis.xray_file") as mock_xray:
                mock_xray.return_value = fake
                result = run_analysis(tmp_path, days=30, include_ci=False, xray_top=1)
        assert result.files[0].functions[0].name == "f"
        assert result.summary.xrayed_files == 1

    def test_xray_top_zero_disables(self, tmp_path):
        (tmp_path / "mod.py").write_text("def f():\n    return 1\n")
        (tmp_path / ".git").mkdir()
        from unittest.mock import patch

        from black_box_unlock.analysis import run_analysis

        with patch("black_box_unlock.analysis.fetch_git_history") as mock_hist:
            mock_hist.return_value = self._history()
            with patch("black_box_unlock.analysis.xray_file") as mock_xray:
                result = run_analysis(tmp_path, days=30, include_ci=False, xray_top=0)
        mock_xray.assert_not_called()
        assert result.summary.xrayed_files == 0

    def test_xray_failure_degrades_gracefully(self, tmp_path):
        (tmp_path / "mod.py").write_text("def f():\n    return 1\n")
        (tmp_path / ".git").mkdir()
        from unittest.mock import patch

        from black_box_unlock.analysis import run_analysis

        with patch("black_box_unlock.analysis.fetch_git_history") as mock_hist:
            mock_hist.return_value = self._history()
            with patch("black_box_unlock.analysis.xray_file") as mock_xray:
                mock_xray.side_effect = RuntimeError("boom")
                result = run_analysis(tmp_path, days=30, include_ci=False, xray_top=1)
        assert result.files[0].functions == []
        assert result.summary.xrayed_files == 0
```

- [ ] **Step 2: Run to verify failure** — `uv run pytest tests/unit/test_analysis.py -v -p no:randomly --no-cov -k Xray` → TypeError (unexpected `xray_top`)

- [ ] **Step 3: Implement** — in `analysis.py`: add import `from .git.xray import xray_file`; change signature to `run_analysis(repo_path, days=30, min_coupling=0.3, include_ci=True, xray_top=5)`; after `files.sort(...)` insert:

```python
    # Auto X-Ray: per-function churn for the top hotspots (JSON/MCP only)
    xrayed = 0
    if xray_top > 0:
        for f in files[:xray_top]:
            if not (repo_path / f.path).exists():
                continue
            try:
                f.functions = xray_file(repo_path, f.path, days=days).functions
                xrayed += 1
            except Exception as e:
                logger.warning("X-Ray failed for {}: {}", f.path, e)
```

and pass `xrayed_files=xrayed` into `AnalysisSummary(...)`. Update `run_analysis`'s docstring Args accordingly.

- [ ] **Step 4: Run full suite** — `uv run pytest -q` → all PASS
- [ ] **Step 5: Commit** — `git add src/black_box_unlock/analysis.py tests/unit/test_analysis.py && git commit -m "feat(analysis): auto X-Ray top hotspot files into FileForensics.functions"`

---

### Task 7: CLI — `bbu xray` and `--xray-top`

**Files:**
- Modify: `src/black_box_unlock/cli.py` (new command after `validate`; new option on `analyze_repo`)
- Test: `tests/unit/test_cli.py` (append)

- [ ] **Step 1: Write the failing tests** (append)

```python
from black_box_unlock.core.models import FileXRay, FunctionChurn


def _xray_result() -> FileXRay:
    return FileXRay(
        path="mod.py", days=365, revisions_analyzed=4, revision_cap_hit=False,
        functions=[
            FunctionChurn(
                name="alpha", start_line=1, end_line=3, revisions=3,
                lines_added=6, lines_deleted=2, complexity=2.0,
            )
        ],
    )


class TestXrayCommand:
    def test_outputs_json(self):
        with patch("black_box_unlock.git.xray.xray_file") as mock_xray:
            mock_xray.return_value = _xray_result()
            result = runner.invoke(app, ["xray", "mod.py"])
        assert result.exit_code == 0
        parsed = json.loads(result.stdout)
        assert parsed["functions"][0]["name"] == "alpha"
        assert parsed["functions"][0]["hotspot_score"] == 6.0

    def test_error_exits_nonzero(self):
        from black_box_unlock.core.exceptions import NotAGitRepoError

        with patch("black_box_unlock.git.xray.xray_file") as mock_xray:
            mock_xray.side_effect = NotAGitRepoError("not a repo")
            result = runner.invoke(app, ["xray", "mod.py"])
        assert result.exit_code == 1
        assert "not a repo" in result.output

    def test_passes_options(self):
        with patch("black_box_unlock.git.xray.xray_file") as mock_xray:
            mock_xray.return_value = _xray_result()
            result = runner.invoke(
                app, ["xray", "mod.py", "--days", "90", "--cap", "50", "--repo", "."]
            )
        assert result.exit_code == 0
        kwargs = mock_xray.call_args[1]
        assert kwargs["days"] == 90 and kwargs["rev_cap"] == 50


class TestAnalyzeRepoXrayTop:
    def test_xray_top_forwarded(self):
        mock_result = MagicMock()
        mock_result.files = []
        with patch("black_box_unlock.cli.run_analysis") as mock_run:
            mock_run.return_value = mock_result
            with patch("black_box_unlock.cli.export_to_json") as mock_export:
                mock_export.return_value = "{}"
                result = runner.invoke(app, ["analyze-repo", "--xray-top", "3"])
        assert result.exit_code == 0
        assert mock_run.call_args[1]["xray_top"] == 3
```

- [ ] **Step 2: Run to verify failure** — `uv run pytest tests/unit/test_cli.py -v -p no:randomly --no-cov -k "Xray or xray"` → exit code 2 (no such command/option)

- [ ] **Step 3: Implement** — in `cli.py`:

`analyze_repo`: add parameter `xray_top: int = typer.Option(5, "--xray-top", help="Auto X-Ray the top N hotspot files (0 disables)")` and pass `xray_top=xray_top` to `run_analysis`.

New command after `validate`:

```python
@app.command()
def xray(
    file: str = typer.Argument(..., help="Repo-relative path of the file to X-Ray"),
    repo: Path = typer.Option(Path("."), "--repo", help="Repository root"),
    days: int = typer.Option(365, help="Days of history to analyze"),
    cap: int = typer.Option(200, "--cap", help="Maximum revisions to analyze"),
) -> None:
    """Per-function churn for one file (Tornhill's X-Ray).

    Ranks the file's functions by revisions x indentation complexity so you can
    see which functions drive a hotspot. JSON to stdout.
    """
    from black_box_unlock.git import xray as xray_mod

    try:
        result = xray_mod.xray_file(repo, file, days=days, rev_cap=cap)
    except BlackBoxUnlockError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(code=1) from e
    print(json.dumps(result.model_dump(mode="json"), indent=2))
```

(Module-attribute call so the test patch target `black_box_unlock.git.xray.xray_file` resolves.)

- [ ] **Step 4: Run full suite + lint** — `uv run pytest -q && uv run ruff check . && uv run ruff format .` → all PASS
- [ ] **Step 5: Commit** — `git add src/black_box_unlock/cli.py tests/unit/test_cli.py && git commit -m "feat(cli): bbu xray command and --xray-top option"`

---

### Task 8: MCP tool — `xray_file`

**Files:**
- Modify: `src/black_box_unlock/mcp_server.py` (after `get_flaky_steps`, before `main`)
- Test: `tests/unit/test_mcp_server.py` (append, following its existing patterns)

- [ ] **Step 1: Write the failing test** (append; mirror the file's existing tool-test style — check how existing tools are invoked there and follow it; the assertion core:)

```python
class TestXrayFileTool:
    def test_returns_function_churn_json(self):
        from black_box_unlock.core.models import FileXRay, FunctionChurn

        fake = FileXRay(
            path="mod.py", days=365, revisions_analyzed=2, revision_cap_hit=False,
            functions=[
                FunctionChurn(
                    name="alpha", start_line=1, end_line=3, revisions=2,
                    lines_added=4, lines_deleted=1, complexity=2.0,
                )
            ],
        )
        with patch("black_box_unlock.mcp_server._xray_file") as mock_xray:
            mock_xray.return_value = fake
            from black_box_unlock.mcp_server import xray_file

            out = xray_file("mod.py", repo_path=".", days=365)
        assert out["functions"][0]["hotspot_score"] == 4.0

    def test_bbu_error_becomes_value_error(self):
        from black_box_unlock.core.exceptions import NotAGitRepoError

        with patch("black_box_unlock.mcp_server._xray_file") as mock_xray:
            mock_xray.side_effect = NotAGitRepoError("not a repo")
            from black_box_unlock.mcp_server import xray_file

            with pytest.raises(ValueError, match="not a repo"):
                xray_file("mod.py")
```

- [ ] **Step 2: Run to verify failure** — `uv run pytest tests/unit/test_mcp_server.py -v -p no:randomly --no-cov -k Xray` → ImportError

- [ ] **Step 3: Implement** — in `mcp_server.py`: add `from .git.xray import xray_file as _xray_file` to imports, then:

```python
@mcp.tool()
def xray_file(
    file_path: str,
    repo_path: str = ".",
    days: int = 365,
    revision_cap: int = 200,
) -> dict:
    """Per-function churn for one file (Tornhill's X-Ray).

    Use after get_hotspots: X-Ray a hot file to see which functions drive its
    instability — the highest-scoring functions are the precise refactoring
    and review targets. Python files get exact attribution; other languages
    are ranked by revisions only (complexity unknown).
    """
    try:
        result = _xray_file(Path(repo_path), file_path, days=days, rev_cap=revision_cap)
    except BlackBoxUnlockError as e:
        raise ValueError(str(e)) from e
    return result.model_dump(mode="json")
```

Note: FastMCP wraps tool functions; if the existing tests call tools directly (unwrapped), match whatever access pattern `tests/unit/test_mcp_server.py` already uses for `get_hotspots` (e.g. `.fn` accessor) — keep the new test consistent with that file's convention.

- [ ] **Step 4: Run full suite** — `uv run pytest -q` → all PASS
- [ ] **Step 5: Commit** — `git add src/black_box_unlock/mcp_server.py tests/unit/test_mcp_server.py && git commit -m "feat(mcp): xray_file tool for per-function churn"`

---

### Task 9: Dogfood smoke + docs

**Files:**
- Create: `docs/XRAY.md`
- Modify: `README.md`, `CLAUDE.md`, `CHANGELOG.md`

- [ ] **Step 1: Dogfood** — run `uv run bbu xray src/black_box_unlock/cli.py --days 365` and `uv run bbu analyze-repo --days 240 --no-ci | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['summary']['xrayed_files']); print([f['name'] for f in d['files'][0]['functions']][:5])"`. Expected: plausible function rankings on bbu itself; record one real example for the docs. If attribution looks wrong, stop and investigate before documenting.

- [ ] **Step 2: Write `docs/XRAY.md`** — sections: What it computes (revisions × indentation complexity per function, current-snapshot ranking); How (one `git log -p -U0` pass, injected diff drivers, ast attribution per revision for Python with indentation fallback, hunk-header names elsewhere); Measured performance (0.03s/file windowed on a 17k-commit repo; rev cap 200 like CodeScene); Limitations (renames split identity; non-Python header error tail — decorator/signature edits may attribute to the preceding function; no function-level coupling yet); Reproduce (the dogfood command + real output snippet from Step 1).

- [ ] **Step 3: Update README.md** — features table row: `| **Function X-Ray** | Per-function churn x complexity for hot files (docs/XRAY.md) |`; MCP tools list gains `xray_file`; CLI usage block gains `bbu xray src/hot_file.py  # Per-function churn for one file`.

- [ ] **Step 4: Update CLAUDE.md** — CLI commands block gains `bbu xray FILE --days 365  # Per-function churn (X-Ray, docs/XRAY.md)`; Forensic Signals section gains `- **Function X-Ray**: per-function revisions x complexity for top hotspots and on demand`.

- [ ] **Step 5: Update CHANGELOG.md** — under `## [Unreleased]` / `### Added`:

```markdown
- Function-level forensics (Tornhill X-Ray): per-function churn x complexity via
  `bbu xray FILE`, `xray_file` MCP tool, and auto X-Ray of top hotspots in
  `analyze-repo` (`--xray-top`, default 5) — docs/XRAY.md
```

- [ ] **Step 6: Commit** — `git add docs/XRAY.md README.md CLAUDE.md CHANGELOG.md && git commit -m "docs: function X-Ray usage, method, and limitations"`

---

### Task 10: Finish

- [ ] **Step 1: code-simplifier** — run the `code-simplifier:code-simplifier` agent over `spans.py`, `git/xray.py`, and the cli/mcp/analysis diffs; apply sensible suggestions only.
- [ ] **Step 2: Full verification** — `uv run pytest -v` (all pass incl. integration) and `uv run ruff check . && uv run ruff format --check .` clean. LSP diagnostics clean on changed files.
- [ ] **Step 3: Close** — `bd close BBU-6351`; verify the closure flushed to `.beads/issues.jsonl` (post-upgrade daemon should handle it; if the pre-export guard complains, `bd sync --import-only` then `bd sync --flush-only`).
- [ ] **Step 4: Commit any remaining changes, push** — `git push`.
