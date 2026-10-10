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

from loguru import logger

from ..complexity import indentation_complexity_lines
from ..core.exceptions import GitToolNotFoundError, NotAGitRepoError
from ..core.models import FileXRay, FunctionChurn, FunctionCoupling
from ..spans import FunctionSpan, indentation_spans, python_spans, span_at
from .run import run_git

# Pairs sharing fewer commits than this are noise within a recency window.
MIN_SHARED_REVISIONS = 2

# git's stderr when a path simply did not exist at a revision (the normal
# deletion case) — distinct from a real failure we must surface. git picks
# between the two by whether the path currently exists on disk, so both are
# legitimate absence signals and must stay silent. Caveat: a corrupt/missing
# *tree* object also yields "exists on disk, but not in", so that rare
# corruption is indistinguishable here and degrades silently (git log -p runs
# first and would usually surface it); blob corruption says "bad object" and is
# logged. Narrowing these markers would spuriously warn on real deletions.
_ABSENT_PATH_MARKERS = ("does not exist in", "exists on disk, but not in")

UNSUPPORTED_LANGUAGE = "unsupported language"

_COMMIT_MARKER = "\x01"
_PRETTY_FORMAT = f"{_COMMIT_MARKER}%H"
_HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@ ?(.*)$")
_HEADER_DEF_RE = re.compile(r"\bdef\s+(\w+)")

# Conservative map of extensions to git's built-in diff drivers (userdiff.c).
DIFF_DRIVERS = {
    ".py": "python",
    ".go": "golang",
    ".java": "java",
    ".kt": "kotlin",
    ".rs": "rust",
    ".rb": "ruby",
    ".php": "php",
    ".pl": "perl",
    ".cs": "csharp",
    ".c": "cpp",
    ".h": "cpp",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".cxx": "cpp",
    ".hpp": "cpp",
    ".swift": "swift",
    ".ex": "elixir",
    ".exs": "elixir",
    ".dart": "dart",
    ".m": "objc",
    ".sh": "bash",
    ".bash": "bash",
    ".css": "css",
    ".html": "html",
    ".md": "markdown",
    ".tex": "tex",
    ".f90": "fortran",
    ".pas": "pascal",
    ".scm": "scheme",
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
    """Build gitattributes content mapping known extensions to built-in diff drivers."""
    return "\n".join(f"*{ext} diff={drv}" for ext, drv in sorted(DIFF_DRIVERS.items())) + "\n"


def parse_patch_log(output: str) -> list[CommitPatch]:
    """Parse `git log -p -U0 --pretty=<marker>%H` output into commits with hunks.

    Commits without hunks (binary changes, merges) are dropped.
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


def _attribute_hunk(
    hunk: Hunk, new_spans: list[FunctionSpan], old_spans: list[FunctionSpan]
) -> dict[str, list[int]]:
    """Map function name -> [added, deleted] for one hunk.

    With spans (Python): each added line goes to the innermost span containing
    it in the post-image (new_spans); each deleted line goes to the innermost
    span containing it in the pre-image (old_spans), so a function removed by
    the commit still receives its deletions. Without spans on either side: the
    hunk-header name takes everything.
    """
    out: dict[str, list[int]] = {}
    if not new_spans and not old_spans:
        name = _header_name(hunk.header)
        if name:
            out[name] = [hunk.new_count, hunk.old_count]
        return out
    for line in range(hunk.new_start, hunk.new_start + hunk.new_count):
        span = span_at(new_spans, line)
        if span:
            out.setdefault(span.name, [0, 0])[0] += 1
    for line in range(hunk.old_start, hunk.old_start + hunk.old_count):
        span = span_at(old_spans, line)
        if span:
            out.setdefault(span.name, [0, 0])[1] += 1
    return out


def _git_patch_log(repo_path: Path, file_path: str, days: int) -> str:
    """Run one `git log -p -U0` pass for the file, with diff drivers injected."""
    attrs = tempfile.NamedTemporaryFile("w", suffix=".gitattributes", delete=False)
    attrs.write(_attributes_content())
    attrs.close()
    try:
        return run_git(
            repo_path,
            [
                "log",
                f"--since={days} days ago",
                "--no-renames",
                "-p",
                "-U0",
                f"--pretty=format:{_PRETTY_FORMAT}",
                "--",
                file_path,
            ],
            config=[f"core.attributesFile={attrs.name}"],
            tolerate_unborn=True,
        )
    finally:
        Path(attrs.name).unlink(missing_ok=True)


def _show(repo_path: Path, sha: str, file_path: str) -> str | None:
    """Return file content at a revision; None if absent there (e.g. deletion commit).

    Routes through run_git so the not-a-repo/git-missing guards and non-ASCII
    path handling stay uniform. A path that simply did not exist at ``sha`` is
    the expected case and yields None silently; any other git failure is logged
    (that revision falls back to coarse hunk-header attribution) and also yields
    None, so one bad revision never aborts the whole X-Ray.
    """
    try:
        return run_git(repo_path, ["show", f"{sha}:{file_path}"])
    except (NotAGitRepoError, GitToolNotFoundError, subprocess.CalledProcessError) as e:
        stderr = getattr(e, "stderr", "") or ""
        if not any(marker in stderr for marker in _ABSENT_PATH_MARKERS):
            logger.warning(
                "git show {}:{} failed; X-Ray attribution degraded for this revision: {}",
                sha,
                file_path,
                stderr.strip() or e,
            )
        return None


def _spans_for(source: str) -> list[FunctionSpan]:
    try:
        return python_spans(source)
    except SyntaxError:
        return indentation_spans(source)


def _spans_at(repo_path: Path, rev: str, file_path: str) -> list[FunctionSpan]:
    """Function spans of the file at a revision; empty if the path is absent there."""
    content = _show(repo_path, rev, file_path)
    return _spans_for(content) if content is not None else []


def _function_coupling(
    touched: dict[str, set[str]], names: set[str], min_ratio: float
) -> list[FunctionCoupling]:
    """Same-file function pairs that change together (X-Ray internal coupling).

    A pair is reported when it shares at least MIN_SHARED_REVISIONS commits and
    its ratio (shared / min revisions, Tornhill's formula) meets min_ratio.
    Only functions in `names` participate — coupling never references a
    function the X-Ray output doesn't list.
    """
    ordered = sorted(n for n in names if n in touched)
    pairs: list[FunctionCoupling] = []
    for i, a in enumerate(ordered):
        for b in ordered[i + 1 :]:
            shared = len(touched[a] & touched[b])
            if shared < MIN_SHARED_REVISIONS:
                continue
            pair = FunctionCoupling(
                function_a=a,
                function_b=b,
                shared_revisions=shared,
                revisions_a=len(touched[a]),
                revisions_b=len(touched[b]),
            )
            if pair.coupling_ratio >= min_ratio:
                pairs.append(pair)
    pairs.sort(key=lambda c: (-c.coupling_ratio, c.function_a, c.function_b))
    return pairs


def xray_file(
    repo_path: Path,
    file_path: str,
    days: int = 365,
    rev_cap: int = 200,
    min_coupling: float = 0.3,
) -> FileXRay:
    """Compute per-function churn for one file (Tornhill's X-Ray).

    Ranks the file's functions by revisions x current indentation complexity
    and reports function pairs that change together (internal coupling).
    Files whose extension has no diff driver return no functions and a
    ``skipped`` reason instead of guessed names.
    Python files get exact ast attribution per revision; other languages use
    git hunk-header names (complexity 0.0, ranked by revisions).

    Raises:
        NotAGitRepoError: If repo_path is not a git repository.
        GitToolNotFoundError: If the git binary is not installed.
    """
    if Path(file_path).suffix.lower() not in DIFF_DRIVERS:
        return FileXRay(
            path=file_path,
            days=days,
            revisions_analyzed=0,
            revision_cap_hit=False,
            functions=[],
            skipped=UNSUPPORTED_LANGUAGE,
        )
    commits = parse_patch_log(_git_patch_log(repo_path, file_path, days))
    cap_hit = len(commits) > rev_cap
    commits = commits[:rev_cap]  # git log emits newest first
    is_python = file_path.endswith(".py")

    tallies: dict[str, list[int]] = defaultdict(lambda: [0, 0])  # name -> [added, deleted]
    touched: dict[str, set[str]] = defaultdict(set)  # name -> commit shas
    for commit in commits:
        new_spans: list[FunctionSpan] = []
        old_spans: list[FunctionSpan] = []
        if is_python:
            new_spans = _spans_at(repo_path, commit.sha, file_path)
            if any(h.old_count for h in commit.hunks):
                old_spans = _spans_at(repo_path, f"{commit.sha}^", file_path)
        for hunk in commit.hunks:
            for name, (added, deleted) in _attribute_hunk(hunk, new_spans, old_spans).items():
                tallies[name][0] += added
                tallies[name][1] += deleted
                touched[name].add(commit.sha)

    functions = _build_functions(repo_path, file_path, is_python, tallies, touched)
    functions.sort(key=lambda f: (-f.hotspot_score, -f.revisions, f.name))
    coupling = _function_coupling(touched, {f.name for f in functions}, min_coupling)
    return FileXRay(
        path=file_path,
        days=days,
        revisions_analyzed=len(commits),
        revision_cap_hit=cap_hit,
        functions=functions,
        coupling=coupling,
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
                name=name,
                revisions=len(touched[name]),
                lines_added=added,
                lines_deleted=deleted,
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
