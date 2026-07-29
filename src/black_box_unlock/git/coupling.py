"""Temporal coupling detection from git history."""

from collections import defaultdict
from dataclasses import dataclass
from itertools import combinations

from ..core.models import DEFAULT_MAX_COUPLED_FILES_PER_COMMIT, TemporalCoupling
from .log import Commit


@dataclass(frozen=True)
class CouplingAnalysis:
    """Coupling pairs plus the bulk changesets excluded from pair generation."""

    couplings: list[TemporalCoupling]
    ignored_large_changesets: int


def analyze_temporal_coupling(
    commits: list[Commit],
    min_ratio: float = 0.3,
    max_changeset_size: int = DEFAULT_MAX_COUPLED_FILES_PER_COMMIT,
) -> CouplingAnalysis:
    """Detect files that change together frequently.

    Every file revision contributes to the denominator. Changesets above
    max_changeset_size do not generate pairs because bulk migrations, vendoring,
    and formatting commits create quadratic work and meaningless coupling.

    Args:
        commits: Commit history from fetch_git_history.
        min_ratio: Minimum coupling ratio to include (default 0.3 = 30%).
        max_changeset_size: Largest commit that contributes co-change pairs.

    Returns:
        Coupling pairs at or above the threshold and the number of excluded
        bulk changesets.
    """
    if max_changeset_size < 2:
        raise ValueError("max_changeset_size must be at least 2")

    commit_counts: dict[str, int] = defaultdict(int)
    co_change_counts: dict[tuple[str, str], int] = defaultdict(int)
    ignored_large_changesets = 0

    for commit in commits:
        files = sorted({f.path for f in commit.files})

        for path in files:
            commit_counts[path] += 1

        if len(files) > max_changeset_size:
            ignored_large_changesets += 1
            continue

        for file_a, file_b in combinations(files, 2):
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
    included = [c for c in couplings if c.coupling_ratio >= min_ratio]
    included.sort(key=lambda c: (-c.coupling_ratio, c.file_a, c.file_b))
    return CouplingAnalysis(
        couplings=included,
        ignored_large_changesets=ignored_large_changesets,
    )


def detect_temporal_coupling(  # [3b] Find co-changing files
    commits: list[Commit],
    min_ratio: float = 0.3,
    max_changeset_size: int = DEFAULT_MAX_COUPLED_FILES_PER_COMMIT,
) -> list[TemporalCoupling]:
    """Compatibility interface returning only the detected coupling pairs."""
    return analyze_temporal_coupling(
        commits,
        min_ratio=min_ratio,
        max_changeset_size=max_changeset_size,
    ).couplings
