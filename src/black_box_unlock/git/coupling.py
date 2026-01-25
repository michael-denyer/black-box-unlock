"""Temporal coupling detection from git history."""

from collections import defaultdict
from itertools import combinations
from typing import Any

from ..core.models import TemporalCoupling


def detect_temporal_coupling(  # [3b] Find co-changing files
    gmap_data: dict[str, Any],
    min_ratio: float = 0.3,
) -> list[TemporalCoupling]:
    """Detect files that change together frequently.

    Args:
        gmap_data: Parsed JSON from gmap export --json.
        min_ratio: Minimum coupling ratio to include (default 0.3 = 30%).

    Returns:
        List of TemporalCoupling pairs above the threshold, sorted by ratio descending.
    """
    commit_counts: dict[str, int] = defaultdict(int)
    co_change_counts: dict[tuple[str, str], int] = defaultdict(int)

    for entry in gmap_data.get("entries", []):
        files = [f["path"] for f in entry.get("files", [])]

        for path in files:
            commit_counts[path] += 1

        for file_a, file_b in combinations(sorted(files), 2):
            co_change_counts[(file_a, file_b)] += 1

    couplings = [
        TemporalCoupling(
            file_a=file_a,
            file_b=file_b,
            co_change_count=co_changes,
            commits_a=commit_counts[file_a],
            commits_b=commit_counts[file_b],
        )
        for (file_a, file_b), co_changes in co_change_counts.items()
    ]

    return [c for c in couplings if c.coupling_ratio >= min_ratio]
