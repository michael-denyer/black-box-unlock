"""MCP server exposing forensic signals as agent context.

Run with: bbu-mcp (stdio transport). Register in Claude Code via the
black-box-unlock plugin or .mcp.json.
"""

from pathlib import Path

from mcp.server.fastmcp import FastMCP

from .analysis import run_analysis
from .core.models import AnalysisResult, FileForensics

mcp = FastMCP("black-box-unlock")

_cache: dict[tuple[str, int], AnalysisResult] = {}


def _analysis(repo_path: str, days: int) -> AnalysisResult:
    """Run (or reuse) an analysis for a repo/window pair."""
    key = (str(Path(repo_path).resolve()), days)
    if key not in _cache:
        _cache[key] = run_analysis(Path(repo_path), days=days)
    return _cache[key]


def _file_dict(f: FileForensics) -> dict:
    return f.model_dump(mode="json")


@mcp.tool()
def get_hotspots(repo_path: str = ".", days: int = 30, top_n: int = 10) -> list[dict]:
    """Top hotspot files (commits x complexity), with bug-fix and CI failure counts.

    Use this to prioritize code review and refactoring: the highest-scoring
    files are the unstable, complex code where defects concentrate.
    """
    result = _analysis(repo_path, days)
    return [_file_dict(f) for f in result.files[:top_n]]


@mcp.tool()
def get_file_forensics(file_path: str, repo_path: str = ".", days: int = 30) -> dict:
    """Full forensic record for one file: churn, complexity, authors, coupling, CI failures."""
    result = _analysis(repo_path, days)
    for f in result.files:
        if f.path == file_path:
            return _file_dict(f)
    return {"error": f"No history for {file_path} in the last {days} days"}


@mcp.tool()
def get_coupled_files(file_path: str, repo_path: str = ".", days: int = 30) -> list[dict]:
    """Files that change together with the given file (hidden dependencies).

    Warn before editing: if you change this file, its coupled files
    historically change too - missing them is a common defect source.
    """
    result = _analysis(repo_path, days)
    for f in result.files:
        if f.path == file_path:
            return [c.model_dump() for c in f.coupled_with]
    return []


@mcp.tool()
def get_ownership(file_path: str, repo_path: str = ".", days: int = 30) -> dict:
    """Authors of a file and whether it is a coordination risk (>3 authors)."""
    result = _analysis(repo_path, days)
    for f in result.files:
        if f.path == file_path:
            return {
                "path": f.path,
                "authors": f.authors,
                "author_count": f.author_count,
                "is_high_risk": f.is_high_risk,
            }
    return {"error": f"No history for {file_path} in the last {days} days"}


@mcp.tool()
def get_ci_failures(repo_path: str = ".", days: int = 30) -> list[dict]:
    """Files implicated in failing CI runs, most-failing first."""
    result = _analysis(repo_path, days)
    failing = [f for f in result.files if f.build_failures > 0]
    failing.sort(key=lambda f: f.build_failures, reverse=True)
    return [{"path": f.path, "build_failures": f.build_failures} for f in failing]


@mcp.tool()
def get_flaky_steps(repo_path: str = ".", days: int = 30) -> list[dict]:
    """CI steps that failed then passed on re-run (unreliable tests/infra)."""
    result = _analysis(repo_path, days)
    return [s.model_dump(mode="json") for s in result.flaky_steps]


def main() -> None:
    """Entry point for the bbu-mcp console script (stdio transport)."""
    mcp.run()


if __name__ == "__main__":
    main()
