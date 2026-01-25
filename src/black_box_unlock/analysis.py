"""Repository analysis combining git forensics."""

import json
import subprocess
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from .core.models import (
    AnalysisResult,
    AnalysisSummary,
    CouplingInfo,
    FileForensics,
)
from .git.churn import parse_gmap_output
from .git.coupling import detect_temporal_coupling
from .git.ownership import parse_ownership_from_gmap


def _fetch_gmap_data(repo_path: Path, days: int) -> dict:  # [2a.1] Fetch git history via gmap
    """Fetch git history data using gmap CLI."""
    cmd = [
        "gmap",
        "--repo",
        str(repo_path),
        "--since",
        f"{days} days ago",
        "export",
        "--json",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return json.loads(result.stdout)


def run_analysis(  # [2a] Main analysis pipeline
    repo_path: Path,
    days: int = 30,
    min_coupling: float = 0.3,
) -> AnalysisResult:
    """Run complete forensic analysis on a repository.

    Args:
        repo_path: Path to git repository.
        days: Number of days of history to analyze.
        min_coupling: Minimum coupling ratio to include.

    Returns:
        AnalysisResult with file forensics and summary.
    """
    gmap_data = _fetch_gmap_data(repo_path, days)

    # Parse individual analyses
    churn_list = parse_gmap_output(gmap_data)
    ownership_list = parse_ownership_from_gmap(gmap_data)
    coupling_list = detect_temporal_coupling(gmap_data, min_ratio=min_coupling)

    # Index by path for joining
    churn_by_path = {c.path: c for c in churn_list}
    ownership_by_path = {o.path: o for o in ownership_list}

    # Build coupling lookup: for each file, which files is it coupled with?
    coupling_by_file: dict[str, list[CouplingInfo]] = defaultdict(list)
    for coupling in coupling_list:
        coupling_by_file[coupling.file_a].append(
            CouplingInfo(file=coupling.file_b, ratio=coupling.coupling_ratio)
        )
        coupling_by_file[coupling.file_b].append(
            CouplingInfo(file=coupling.file_a, ratio=coupling.coupling_ratio)
        )

    # All unique paths
    all_paths = set(churn_by_path.keys()) | set(ownership_by_path.keys())

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
                authors=ownership.authors if ownership else [],
                coupled_with=coupling_by_file.get(path, []),
            )
        )

    # Sort by hotspot_score descending
    files.sort(key=lambda f: f.hotspot_score, reverse=True)

    # Compute summary
    high_risk_count = sum(1 for f in files if f.is_high_risk)
    coupled_pairs = len(coupling_list)

    repo_name = repo_path.name

    return AnalysisResult(
        repo=repo_name,
        analyzed_days=days,
        generated_at=datetime.now(timezone.utc),
        files=files,
        summary=AnalysisSummary(
            total_files=len(files),
            high_risk_ownership=high_risk_count,
            coupled_pairs=coupled_pairs,
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
