"""MCP server exposing forensic signals as agent context.

Run with: bbu-mcp (stdio transport). Register in Claude Code via the
black-box-unlock plugin or .mcp.json.

Results are cached per (repo, days, include_ci) for the server process lifetime;
restart the server to pick up new commits.
"""

from pathlib import Path

from mcp.server.fastmcp import FastMCP

from .analysis import run_analysis
from .core.exceptions import BlackBoxUnlockError
from .core.models import AnalysisResult, FileForensics
from .git.xray import xray_file as _xray_file

mcp = FastMCP("black-box-unlock")

_cache: dict[tuple[str, int, bool], AnalysisResult] = {}


def _analysis(repo_path: str, days: int, include_ci: bool = False) -> AnalysisResult:
    """Run (or reuse) an analysis for a (repo, days, include_ci) triple."""
    key = (str(Path(repo_path).resolve()), days, include_ci)
    if key not in _cache:
        _cache[key] = run_analysis(Path(repo_path), days=days, include_ci=include_ci)
    return _cache[key]


def _safe_analysis(repo_path: str, days: int, include_ci: bool = False) -> AnalysisResult:
    """Call _analysis and surface BlackBoxUnlockError as ValueError on the MCP error channel."""
    try:
        return _analysis(repo_path, days, include_ci)
    except BlackBoxUnlockError as e:
        raise ValueError(str(e)) from e


def _file_dict(f: FileForensics) -> dict:
    return f.model_dump(mode="json")


@mcp.tool()
def get_hotspots(
    repo_path: str = ".",
    days: int = 30,
    top_n: int = 10,
    include_ci: bool = False,
) -> list[dict]:
    """Top hotspot files (commits x complexity), with bug-fix and CI failure counts.

    Use this to prioritize code review and refactoring: the highest-scoring
    files are the unstable, complex code where defects concentrate.

    Set include_ci=True to include CI build-failure counts; slower, needs gh.
    """
    result = _safe_analysis(repo_path, days, include_ci)
    return [_file_dict(f) for f in result.files[:top_n]]


@mcp.tool()
def get_file_forensics(
    file_path: str,
    repo_path: str = ".",
    days: int = 30,
    include_ci: bool = False,
) -> dict:
    """Full forensic record for one file: churn, complexity, authors, coupling, CI failures.

    Set include_ci=True to include CI build-failure counts; slower, needs gh.
    """
    result = _safe_analysis(repo_path, days, include_ci)
    for f in result.files:
        if f.path == file_path:
            return _file_dict(f)
    raise ValueError(f"No history for {file_path} in the last {days} days")


@mcp.tool()
def get_coupled_files(
    file_path: str,
    repo_path: str = ".",
    days: int = 30,
    include_ci: bool = False,
) -> list[dict]:
    """Files that change together with the given file (hidden dependencies).

    Warn before editing: if you change this file, its coupled files
    historically change too - missing them is a common defect source.

    Set include_ci=True to include CI build-failure counts; slower, needs gh.
    """
    result = _safe_analysis(repo_path, days, include_ci)
    for f in result.files:
        if f.path == file_path:
            return [c.model_dump(mode="json") for c in f.coupled_with]
    return []


@mcp.tool()
def get_ownership(
    file_path: str,
    repo_path: str = ".",
    days: int = 30,
    include_ci: bool = False,
) -> dict:
    """Authors of a file and whether it is a coordination risk (>3 authors).

    Set include_ci=True to include CI build-failure counts; slower, needs gh.
    """
    result = _safe_analysis(repo_path, days, include_ci)
    for f in result.files:
        if f.path == file_path:
            return {
                "path": f.path,
                "authors": f.authors,
                "author_count": f.author_count,
                "is_high_risk": f.is_high_risk,
            }
    raise ValueError(f"No history for {file_path} in the last {days} days")


@mcp.tool()
def get_ci_failures(repo_path: str = ".") -> list[dict]:
    """Files implicated in failing CI runs, most-failing first.

    Scans the repository's last 100 workflow runs (not limited by a day window).
    """
    # days=30: canonical window for cache reuse; CI signals are run-count-based, not day-based
    result = _safe_analysis(repo_path, 30, include_ci=True)
    failing = [f for f in result.files if f.build_failures > 0]
    failing.sort(key=lambda f: f.build_failures, reverse=True)
    return [{"path": f.path, "build_failures": f.build_failures} for f in failing]


@mcp.tool()
def get_flaky_steps(repo_path: str = ".") -> list[dict]:
    """CI steps that failed then passed on re-run (unreliable tests/infra).

    Scans the repository's last 100 workflow runs (not limited by a day window).
    """
    # days=30: canonical window for cache reuse; CI signals are run-count-based, not day-based
    result = _safe_analysis(repo_path, 30, include_ci=True)
    return [s.model_dump(mode="json") for s in result.flaky_steps]


@mcp.tool()
def xray_file(
    file_path: str,
    repo_path: str = ".",
    days: int = 365,
    revision_cap: int = 200,
) -> dict:
    """Per-function churn for one file (Tornhill's X-Ray).

    Use after get_hotspots: X-Ray a hot file to see which functions drive its
    instability - the highest-scoring functions are the precise refactoring
    and review targets. Python files get exact attribution; other languages
    are ranked by revisions only (complexity unknown).
    """
    try:
        result = _xray_file(Path(repo_path), file_path, days=days, rev_cap=revision_cap)
    except BlackBoxUnlockError as e:
        raise ValueError(str(e)) from e
    return result.model_dump(mode="json")


def main() -> None:
    """Entry point for the bbu-mcp console script (stdio transport)."""
    mcp.run()


if __name__ == "__main__":
    main()
