"""MCP server exposing forensic signals as agent context.

Run with: bbu-mcp (stdio transport). Register in Claude Code via the
black-box-unlock plugin or .mcp.json.

Results are cached per (repo, HEAD oid, days, include_ci, hour) in a small LRU,
so a new commit or a new hour triggers a fresh analysis. Every result carries a
``provenance`` object saying which HEAD it read and whether the cache served it.
"""

import os
import subprocess
import time
from collections import OrderedDict
from pathlib import Path
from typing import Literal

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from .analysis import build_provenance, run_analysis
from .core.exceptions import BlackBoxUnlockError
from .core.models import AnalysisResult, FileForensics
from .git.changes import BaseChange, StagedChange, WorkingTreeChange
from .git.ownership import ownership_risk
from .git.run import head_oid, run_git
from .git.xray import xray_file as _xray_file
from .path_roles import PathRole
from .review import ChangeReviewRequest
from .review import run_change_review as _run_change_review

mcp = MCPServer("black-box-unlock")  # [1b] MCP server - forensic signals as agent tools

_CACHE_SIZE = 8
_cache: OrderedDict[tuple[str, str | None, int, bool, int], AnalysisResult] = OrderedDict()


def _hour_bucket() -> int:
    return int(time.time() // 3600)


def _analysis(repo_path: str, days: int, include_ci: bool = False) -> AnalysisResult:
    """Run (or reuse) an analysis for the repo's current HEAD.

    The key holds the HEAD oid and the current hour, so a new commit or a
    rolled ``--days`` window forces a re-run. X-Ray is off here: ``xray_file``
    is the on-demand path.
    """
    root = Path(repo_path).resolve()
    oid = head_oid(root)
    key = (str(root), oid, days, include_ci, _hour_bucket())
    hit = _cache.get(key)
    if hit is not None:
        _cache.move_to_end(key)
        if hit.provenance is None:
            return hit
        provenance = hit.provenance.model_copy(update={"cached": True})
        return hit.model_copy(update={"provenance": provenance})
    result = run_analysis(root, days=days, include_ci=include_ci, xray_top=0)
    result = result.model_copy(
        update={
            "provenance": build_provenance(
                root, days, include_ci, oid=oid, analysed_at=result.generated_at
            )
        }
    )
    _cache[key] = result
    while len(_cache) > _CACHE_SIZE:
        _cache.popitem(last=False)
    return result


def _safe_analysis(repo_path: str, days: int, include_ci: bool = False) -> AnalysisResult:
    """Call _analysis and surface BlackBoxUnlockError as a ToolError so the message reaches the client."""
    try:
        return _analysis(repo_path, days, include_ci)
    except BlackBoxUnlockError as e:
        raise ToolError(str(e)) from e


def _parse_roles(roles: list[str] | None) -> set[PathRole] | None:
    """Validate role names at the tool boundary."""
    if roles is None:
        return None
    if not roles:
        raise ToolError("roles must not be empty; omit it to return every role")
    valid = {role.value for role in PathRole}
    unknown = sorted(set(roles) - valid)
    if unknown:
        raise ToolError(f"Unknown path role(s) {unknown}; valid roles: {sorted(valid)}")
    return {PathRole(name) for name in roles}


def _file_dict(f: FileForensics) -> dict:
    return f.model_dump(mode="json")


def _provenance(result: AnalysisResult) -> dict | None:
    return result.provenance.model_dump(mode="json") if result.provenance else None


def _repo_relative(repo_path: str, file_path: str) -> str:
    """Return file_path relative to the repo root without following the file's own symlink.

    Git records a tracked symlink under its own path, so only the root is
    resolved. An absolute file_path is accepted under either the given or the
    resolved root (macOS /tmp versus /private/tmp).

    Raises:
        ToolError: If the path lies outside the repository, or is a directory.
    """
    given_root = Path(repo_path).absolute()
    root = given_root.resolve()
    candidate = Path(file_path)
    joined = candidate if candidate.is_absolute() else root / candidate
    normalised = Path(os.path.normpath(joined))
    for base in (root, given_root):
        if normalised.is_relative_to(base):
            rel = normalised.relative_to(base).as_posix()
            break
    else:
        raise ToolError(f"{file_path} is outside the repository at {root}")
    target = root / rel
    if rel == "." or (target.is_dir() and not target.is_symlink()):
        raise ToolError(f"{file_path} is a directory; name a file")
    return rel


def _in_tree(repo_path: str, rel: str) -> bool:
    """True when git tracks rel in the index or at HEAD; untracked and ignored files are not."""
    root = Path(repo_path).resolve()
    try:
        run_git(root, ["ls-files", "--error-unmatch", "--", rel])
        return True
    except subprocess.CalledProcessError:
        pass
    try:
        return bool(run_git(root, ["ls-tree", "HEAD", "--", rel]).strip())
    except subprocess.CalledProcessError:
        return False


def _no_history(repo_path: str, rel: str, days: int) -> ToolError:
    """Say why a path has no record: absent from the tree, or present but quiet in the window."""
    if _in_tree(repo_path, rel):
        return ToolError(f"{rel} exists but has no history in the last {days} days")
    return ToolError(f"{rel} is not in the repository tree")


def _find_file(repo_path: str, file_path: str, days: int, result: AnalysisResult) -> FileForensics:
    rel = _repo_relative(repo_path, file_path)
    for f in result.files:
        if f.path == rel:
            return f
    raise _no_history(repo_path, rel, days)


@mcp.tool()
def get_hotspots(
    repo_path: str = ".",
    days: int = 30,
    top_n: int = 10,
    include_ci: bool = False,
    roles: list[str] | None = None,
) -> dict:
    """Top hotspot files (commits x complexity), with bug-fix and CI failure counts.

    Use this to prioritize code review and refactoring: the highest-scoring
    files are the unstable, complex code where defects concentrate.

    Returns {"hotspots": [...], "provenance": {...}}. ``provenance`` names the
    HEAD oid analysed, when, the window, whether the repo is a shallow clone
    (history is truncated), the bbu version, and whether this call hit the
    cache. The cache follows HEAD, so a new commit is reflected. Per-function
    X-Ray is not included here; call xray_file for it.

    Set include_ci=True to include CI build-failure counts; slower, needs gh.
    Set roles (source, test, docs, config, migration, generated, other) to keep
    only files with those path roles; the filter runs before top_n.
    """
    wanted = _parse_roles(roles)
    result = _safe_analysis(repo_path, days, include_ci)
    files = [f for f in result.files if wanted is None or f.path_role in wanted]
    return {
        "hotspots": [_file_dict(f) for f in files[:top_n]],
        "provenance": _provenance(result),
    }


@mcp.tool()
def get_file_forensics(
    file_path: str,
    repo_path: str = ".",
    days: int = 30,
    include_ci: bool = False,
) -> dict:
    """Full forensic record for one file: churn, complexity, authors, coupling, CI failures.

    file_path may be repo-relative or an absolute path inside the repo. Errors
    distinguish a path outside the repo, a path not in the tree, and a path
    with no history in the window. The result has a ``provenance`` object (HEAD
    oid, time, window, shallow-clone flag, cache hit). Functions are not
    included; call xray_file.

    Set include_ci=True to include CI build-failure counts; slower, needs gh.
    """
    result = _safe_analysis(repo_path, days, include_ci)
    found = _find_file(repo_path, file_path, days, result)
    return {**_file_dict(found), "provenance": _provenance(result)}


@mcp.tool()
def get_coupled_files(
    file_path: str,
    repo_path: str = ".",
    days: int = 30,
    include_ci: bool = False,
) -> dict:
    """Files that change together with the given file (hidden dependencies).

    Warn before editing: if you change this file, its coupled files
    historically change too - missing them is a common defect source.
    A partner is listed when rate_to_partner (the share of this file's
    revisions that also changed it) reaches the coupling policy's min_ratio
    and the pair has min_shared_revisions shared revisions. Commits touching
    more than max_changeset_size files and partners deleted at HEAD are
    excluded. The policy comes from the [coupling] table of .bbu.toml.

    Returns {"coupled_files": [...], "provenance": {...}}. file_path may be
    repo-relative or absolute inside the repo; an unknown path raises instead
    of returning an empty list.

    Set include_ci=True to include CI build-failure counts; slower, needs gh.
    """
    result = _safe_analysis(repo_path, days, include_ci)
    found = _find_file(repo_path, file_path, days, result)
    return {
        "coupled_files": [c.model_dump(mode="json") for c in found.coupled_with],
        "provenance": _provenance(result),
    }


@mcp.tool()
def get_ownership(
    file_path: str,
    repo_path: str = ".",
    days: int = 30,
    include_ci: bool = False,
) -> dict:
    """Who owns a file, how concentrated that is, and how recently it was touched.

    Bot commits are ignored for all three numbers below. Authors are
    ``.mailmap``-resolved emails.

    - ``main_author`` and ``main_author_share``: the author with the most
      commits in the window, and their fraction of the file's commits. Read
      the share first. At or above 0.5 the file has an owner even with many
      authors. Below 0.5 with more than 3 authors it is diffuse, a
      coordination risk (``ownership_risk`` is ``diffuse``). ``shared`` means
      more than 3 authors but one holds half or more. ``owned`` means 3 or
      fewer authors. ``main_author_share`` is 0.0 when no human touched it.
    - ``last_active``: ISO time of the latest non-bot commit in the window.
      Use it to ask who to consult. A main author whose last commit is old may
      have left. The window bounds it, so a file untouched all window is
      absent, and ``orphaned`` is never reported here.
    - ``author_count`` and ``authors``: the raw spread. ``is_high_risk`` is
      the older count-only test (>3 authors) and ignores the share.

    file_path may be repo-relative or absolute inside the repo. The result has
    a ``provenance`` object.

    Set include_ci=True to include CI build-failure counts; slower, needs gh.
    """
    result = _safe_analysis(repo_path, days, include_ci)
    f = _find_file(repo_path, file_path, days, result)
    return {
        "path": f.path,
        "authors": f.authors,
        "author_count": f.author_count,
        "main_author": f.main_author,
        "main_author_share": f.main_author_share,
        "last_active": f.last_active.isoformat() if f.last_active else None,
        "ownership_risk": ownership_risk(f).value,
        "is_high_risk": f.is_high_risk,
        "provenance": _provenance(result),
    }


@mcp.tool()
def get_ci_failures(repo_path: str = ".") -> dict:
    """Failed CI runs and implicated files, with most-failing files first.

    Scans workflow runs created in the last 30 days (at most 10 pages of 100).
    Changed paths are correlated with the failed run, not proven causal.
    The result has a ``provenance`` object.
    """
    # days=30: canonical window for cache reuse; CI runs are bounded to the same window
    result = _safe_analysis(repo_path, 30, include_ci=True)
    failing = [f for f in result.files if f.build_failures > 0]
    failing.sort(key=lambda f: f.build_failures, reverse=True)
    return {
        "status": result.ci_status.state.value,
        "errors": result.ci_status.errors,
        "files": [{"path": f.path, "build_failures": f.build_failures} for f in failing],
        "runs": [run.model_dump(mode="json") for run in result.failed_ci_runs],
        "provenance": _provenance(result),
    }


@mcp.tool()
def get_flaky_steps(repo_path: str = ".") -> dict:
    """CI steps that failed then passed on re-run (unreliable tests/infra).

    Scans workflow runs created in the last 30 days (at most 10 pages of 100).
    The result has a ``provenance`` object.
    """
    # days=30: canonical window for cache reuse; CI runs are bounded to the same window
    result = _safe_analysis(repo_path, 30, include_ci=True)
    return {
        "status": result.ci_status.state.value,
        "errors": result.ci_status.errors,
        "steps": [s.model_dump(mode="json") for s in result.flaky_steps],
        "provenance": _provenance(result),
    }


@mcp.tool()
def xray_file(
    file_path: str,
    repo_path: str = ".",
    days: int = 365,
    revision_cap: int = 200,
    min_coupling: float = 0.3,
) -> dict:
    """Per-function churn for one file (Tornhill's X-Ray).

    Use after get_hotspots: X-Ray a hot file to see which functions drive its
    instability - the highest-scoring functions are the precise refactoring
    and review targets. The coupling list shows function pairs that change
    together (>= min_coupling ratio): edit one, check its partners. Python
    files get exact attribution; other languages with a git diff driver are
    ranked by revisions only; extensions without one return no functions and
    "skipped": "unsupported language".

    file_path may be repo-relative or absolute inside the repo. Always computed
    fresh from git, never cached; the result has a ``provenance`` object.
    """
    try:
        root = Path(repo_path).resolve()
        rel = _repo_relative(repo_path, file_path)
        result = _xray_file(
            root,
            rel,
            days=days,
            rev_cap=revision_cap,
            min_coupling=min_coupling,
        )
        if result.revisions_analyzed == 0 and (
            result.skipped is None or not _in_tree(repo_path, rel)
        ):
            raise _no_history(repo_path, rel, days)
        provenance = build_provenance(root, days, False, oid=head_oid(root))
    except BlackBoxUnlockError as e:
        raise ToolError(str(e)) from e
    return {**result.model_dump(mode="json"), "provenance": provenance.model_dump(mode="json")}


@mcp.tool()
def review_change(
    repo_path: str = ".",
    mode: Literal["base", "staged", "working_tree"] = "working_tree",
    base_ref: str = "origin/main",
    profile: str | None = None,
    days: int | None = None,
    min_coupling: float | None = None,
    min_shared_revisions: int | None = None,
    include_ci: bool | None = None,
) -> dict:
    """Review a current change and return at most three evidence-backed actions.

    ``base`` includes branch commits and all local layers from the merge base.
    ``staged`` reads only the index. ``working_tree`` reads unstaged and
    untracked files. Review always runs fresh. CI stays off unless a selected
    profile or ``include_ci`` turns it on. ``min_coupling`` and
    ``min_shared_revisions`` override the ``.bbu.toml`` coupling policy;
    ``min_coupling`` applies to the share of the changed file's revisions
    that also changed the partner.
    """
    selectors = {
        "base": BaseChange(base_ref=base_ref),
        "staged": StagedChange(),
        "working_tree": WorkingTreeChange(),
    }
    try:
        result = _run_change_review(
            Path(repo_path),
            ChangeReviewRequest(
                selector=selectors[mode],
                profile=profile,
                days=days,
                min_coupling=min_coupling,
                min_shared_revisions=min_shared_revisions,
                include_ci=include_ci,
            ),
        )
    except BlackBoxUnlockError as error:
        raise ToolError(str(error)) from error
    return result.model_dump(mode="json")


def main() -> None:
    """Entry point for the bbu-mcp console script (stdio transport)."""
    mcp.run()


if __name__ == "__main__":
    main()
