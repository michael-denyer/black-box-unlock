"""Repository analysis combining git forensics."""

import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from loguru import logger

from .cicd.github_actions import collect_ci_signals
from .cicd.models import CIAnalysis
from .complexity import indentation_complexity
from .core.models import (
    AnalysisParameters,
    AnalysisResult,
    AnalysisSummary,
    CouplingInfo,
    FileForensics,
    SignalState,
    SignalStatus,
    coupling_info_for,
    coupling_info_sort_key,
)
from .git.churn import parse_history_entries
from .git.coupling import analyze_temporal_coupling
from .git.defects import bugfix_counts
from .git.log import fetch_git_history
from .git.ownership import parse_ownership_from_history
from .git.xray import xray_file


def run_analysis(  # [2a] Main analysis pipeline
    repo_path: Path,
    days: int = 30,
    min_coupling: float = 0.3,
    include_ci: bool = True,
    xray_top: int = 5,
    *,
    ensure_paths: frozenset[str] = frozenset(),
) -> AnalysisResult:
    """Run complete forensic analysis on a repository.

    Complexity is measured from current file contents: files deleted or renamed
    within the window score 0 and drop from the hotspot ranking.

    Args:
        repo_path: Path to git repository.
        days: Number of days of history to analyze.
        min_coupling: Minimum coupling ratio to include.
        include_ci: Whether to include CI/CD build failure data.
        xray_top: Auto X-Ray the top N hotspot files (0 disables).
        ensure_paths: Current paths to include even when they have no history.

    Returns:
        AnalysisResult with file forensics and summary.
    """
    history = fetch_git_history(repo_path, days)

    ci_analysis = CIAnalysis(
        status=SignalStatus(state=SignalState.disabled),
    )
    if include_ci:
        ci_analysis = collect_ci_signals(repo_path=repo_path, limit=100)
        for error in ci_analysis.status.errors:
            logger.warning("CI data degraded: {}", error)

    # Parse individual analyses
    churn_list = parse_history_entries(history)
    ownership_list = parse_ownership_from_history(history)
    coupling_analysis = analyze_temporal_coupling(history, min_ratio=min_coupling)
    coupling_list = coupling_analysis.couplings
    defect_counts = bugfix_counts(history)

    # Index by path for joining
    churn_by_path = {c.path: c for c in churn_list}
    ownership_by_path = {o.path: o for o in ownership_list}

    # Build coupling lookup: for each file, which files is it coupled with?
    coupling_by_file: dict[str, list[CouplingInfo]] = defaultdict(list)
    for coupling in coupling_list:
        coupling_by_file[coupling.file_a].append(coupling_info_for(coupling, coupling.file_a))
        coupling_by_file[coupling.file_b].append(coupling_info_for(coupling, coupling.file_b))
    for coupled_files in coupling_by_file.values():
        coupled_files.sort(key=coupling_info_sort_key)

    # All unique paths
    all_paths = (
        set(churn_by_path.keys())
        | set(ownership_by_path.keys())
        | set(ci_analysis.file_failures.keys())
        | set(ensure_paths)
    )

    # Build FileForensics for each file
    files: list[FileForensics] = []
    for path in all_paths:
        churn = churn_by_path.get(path)
        ownership = ownership_by_path.get(path)

        files.append(
            FileForensics(
                path=path,
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
                f.functions = xray_file(repo_path, f.path, days=days).functions
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
            min_coupling=min_coupling,
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
            ignored_large_changesets=coupling_analysis.ignored_large_changesets,
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
