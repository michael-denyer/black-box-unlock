"""Repository analysis combining git forensics."""

import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from loguru import logger

from . import __version__
from .cicd.github_actions import collect_ci_signals
from .cicd.models import CIAnalysis
from .complexity import indentation_complexity
from .config import load_project_config, resolve_coupling_policy
from .core.models import (
    AnalysisParameters,
    AnalysisResult,
    AnalysisSummary,
    CouplingInfo,
    CouplingPolicy,
    FileForensics,
    Provenance,
    SignalState,
    SignalStatus,
    coupling_info_for,
    coupling_info_sort_key,
)
from .git.churn import parse_history_entries
from .git.coupling import analyze_temporal_coupling
from .git.defects import bugfix_counts
from .git.log import Commit, CommitFile, exclude_bulk, fetch_git_history
from .git.ownership import parse_ownership_from_history
from .git.run import head_paths, is_shallow
from .git.xray import xray_file
from .path_roles import classify_path_role


def _canonicalize_history_paths(
    commits: list[Commit],
    path_aliases: dict[str, str],
) -> list[Commit]:
    """Combine renamed paths before per-file history is aggregated."""
    if not path_aliases:
        return commits

    canonical: list[Commit] = []
    for commit in commits:
        files_by_path: dict[str, CommitFile] = {}
        for file in commit.files:
            path = path_aliases.get(file.path, file.path)
            existing = files_by_path.get(path)
            if existing is None:
                files_by_path[path] = file.model_copy(update={"path": path})
                continue
            files_by_path[path] = existing.model_copy(
                update={
                    "added_lines": existing.added_lines + file.added_lines,
                    "deleted_lines": existing.deleted_lines + file.deleted_lines,
                }
            )
        canonical.append(commit.model_copy(update={"files": list(files_by_path.values())}))
    return canonical


def _canonicalize_ci_paths(
    ci_analysis: CIAnalysis,
    path_aliases: dict[str, str],
) -> CIAnalysis:
    """Apply the same renamed-path identity to optional CI evidence."""
    if not path_aliases:
        return ci_analysis

    failed_runs = [
        run.model_copy(
            update={
                "implicated_paths": sorted(
                    {path_aliases.get(path, path) for path in run.implicated_paths}
                )
            }
        )
        for run in ci_analysis.failed_runs
    ]
    file_failures: Counter[str] = Counter()
    for run in failed_runs:
        file_failures.update(run.implicated_paths)
    return ci_analysis.model_copy(
        update={
            "file_failures": dict(file_failures),
            "failed_runs": failed_runs,
        }
    )


def build_provenance(
    repo_path: Path,
    days: int,
    include_ci: bool,
    *,
    oid: str | None,
    analysed_at: datetime | None = None,
) -> Provenance:
    """Describe the repository state an analysis reads (oid is its HEAD)."""
    return Provenance(
        head_oid=oid,
        analysed_at=analysed_at or datetime.now(timezone.utc),
        days=days,
        include_ci=include_ci,
        shallow_clone=is_shallow(repo_path),
        bbu_version=__version__,
    )


def run_analysis(  # [2a] Main analysis pipeline
    repo_path: Path,
    days: int = 30,
    include_ci: bool = True,
    xray_top: int = 5,
    *,
    policy: CouplingPolicy | None = None,
    ensure_paths: frozenset[str] = frozenset(),
    path_aliases: dict[str, str] | None = None,
    rev: str | None = None,
) -> AnalysisResult:
    """Run complete forensic analysis on a repository.

    Complexity is measured from current file contents: files deleted or renamed
    within the window score 0 and drop from the hotspot ranking.

    Bulk commits (more than ``policy.max_changeset_size`` files) are excluded
    from churn, ownership, defects, and coupling. Auto X-Ray reads each file's
    own history and keeps them. A file's ``coupled_with`` lists a partner only
    when the share of the file's revisions that touched it reaches
    ``policy.min_ratio``. With ``policy.require_live_partner``, pairs whose
    side is absent from the tree at ``rev`` (and not in ensure_paths) are
    dropped, so a base-mode review still sees partners of a file the branch
    deletes.

    Args:
        repo_path: Path to git repository.
        days: Number of days of history to analyze.
        include_ci: Whether to include CI/CD build failure data.
        xray_top: Auto X-Ray the top N hotspot files (0 disables).
        policy: Coupling and bulk-commit policy; None reads ``.bbu.toml``.
        ensure_paths: Current paths to include even when they have no history.
        path_aliases: Historical paths mapped to their current renamed path.
        rev: Last revision whose history is analyzed (HEAD when None).

    Returns:
        AnalysisResult with file forensics and summary.
    """
    policy = policy if policy is not None else resolve_coupling_policy(repo_path)
    aliases = path_aliases or {}
    history, bulk_commits = exclude_bulk(
        _canonicalize_history_paths(fetch_git_history(repo_path, days, rev), aliases),
        policy.max_changeset_size,
    )
    live_paths = (
        head_paths(repo_path, rev or "HEAD") | ensure_paths | frozenset(aliases.values())
        if policy.require_live_partner and history
        else None
    )

    ci_analysis = CIAnalysis(
        status=SignalStatus(state=SignalState.disabled),
    )
    if include_ci:
        ci_analysis = collect_ci_signals(repo_path=repo_path, limit=100, days=days)
        ci_analysis = _canonicalize_ci_paths(ci_analysis, aliases)
        for error in ci_analysis.status.errors:
            logger.warning("CI data degraded: {}", error)

    # Parse individual analyses
    churn_list = parse_history_entries(history)
    ownership_list = parse_ownership_from_history(history)
    coupling_analysis = analyze_temporal_coupling(history, policy, live_paths)
    coupling_list = coupling_analysis.couplings
    defect_counts = bugfix_counts(history)

    # Index by path for joining
    churn_by_path = {c.path: c for c in churn_list}
    ownership_by_path = {o.path: o for o in ownership_list}

    # Build coupling lookup: for each file, which files is it coupled with?
    coupling_by_file: dict[str, list[CouplingInfo]] = defaultdict(list)
    for coupling in coupling_list:
        for path in (coupling.file_a, coupling.file_b):
            info = coupling_info_for(coupling, path)
            if info.rate_to_partner >= policy.min_ratio:
                coupling_by_file[path].append(info)
    for coupled_files in coupling_by_file.values():
        coupled_files.sort(key=coupling_info_sort_key)

    # All unique paths
    all_paths = (
        set(churn_by_path.keys())
        | set(ownership_by_path.keys())
        | set(ci_analysis.file_failures.keys())
        | set(ensure_paths)
    )

    path_role_rules = load_project_config(repo_path).path_roles

    # Build FileForensics for each file
    files: list[FileForensics] = []
    for path in all_paths:
        churn = churn_by_path.get(path)
        ownership = ownership_by_path.get(path)

        files.append(
            FileForensics(
                path=path,
                path_role=classify_path_role(path, path_role_rules).role,
                commits=churn.commits if churn else 0,
                lines_changed=churn.total_lines_changed if churn else 0,
                complexity=indentation_complexity(repo_path / path),
                authors=ownership.authors if ownership else [],
                coupled_with=coupling_by_file.get(path, []),
                build_failures=ci_analysis.file_failures.get(path, 0),
                bugfix_commits=defect_counts.get(path, 0),
            )
        )

    # Hotspot score descending; path breaks ties so output is reproducible
    files.sort(key=lambda f: (-f.hotspot_score, f.path))

    # Auto X-Ray: per-function churn for the top hotspots (JSON/MCP only)
    xrayed = 0
    if xray_top > 0:
        for f in files[:xray_top]:
            if not (repo_path / f.path).exists():
                continue
            try:
                xray = xray_file(repo_path, f.path, days=days)
                f.functions = xray.functions
                f.xray_skipped = xray.skipped
                if xray.skipped is None:
                    xrayed += 1
            except Exception as e:
                f.xray_failed = True
                logger.warning("X-Ray failed for {}: {}", f.path, e)

    # Compute summary
    high_risk_count = sum(1 for f in files if f.is_high_risk)
    coupled_pairs = len(coupling_list)

    repo_name = repo_path.resolve().name

    logger.info("Analyzed {} files over {} days", len(files), days)

    return AnalysisResult(
        repo=repo_name,
        analyzed_days=days,
        generated_at=datetime.now(timezone.utc),
        files=files,
        couplings=coupling_list,
        parameters=AnalysisParameters(
            coupling=policy,
            include_ci=include_ci,
            xray_top=xray_top,
        ),
        ci_status=ci_analysis.status,
        failed_ci_runs=ci_analysis.failed_runs,
        flaky_steps=ci_analysis.flaky_steps,
        summary=AnalysisSummary(
            total_files=len(files),
            high_risk_ownership=high_risk_count,
            coupled_pairs=coupled_pairs,
            xrayed_files=xrayed,
            ignored_large_changesets=bulk_commits,
            dropped_deleted_partners=coupling_analysis.dropped_deleted_partners,
        ),
    )


def export_to_json(result: AnalysisResult) -> str:  # [2b] Serialize result to JSON
    """Export analysis result to JSON string.

    Computed properties (hotspot_score, author_count, is_high_risk) are
    automatically included via Pydantic's @computed_field decorator.

    Args:
        result: The analysis result to export.

    Returns:
        JSON string representation.
    """
    return json.dumps(result.model_dump(mode="json"), indent=2)
