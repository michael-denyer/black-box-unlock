"""Per-function churn for one file via git patch parsing (Tornhill's X-Ray).

Engine: one `git log -p -U0` pass with git's built-in language diff drivers
injected via a temp core.attributesFile (an in-repo .gitattributes still wins).
For .py files, each revision's content is fetched and hunks are attributed to
exact ast spans (indentation fallback on SyntaxError); other languages use the
hunk-header function name, which git truncates at ~80 bytes.
"""

import re
from dataclasses import dataclass, field

from ..spans import FunctionSpan, span_at

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
