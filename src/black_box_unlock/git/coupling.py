"""Temporal coupling detection from git history."""

from collections import defaultdict
from dataclasses import dataclass
from itertools import combinations

from ..core.models import (
    CouplingInfo,
    CouplingPolicy,
    TemporalCoupling,
    coupling_info_for,
    coupling_info_sort_key,
)
from .log import Commit


@dataclass(frozen=True)
class CouplingAnalysis:
    """Coupling pairs plus the pairs dropped because a side is gone at HEAD."""

    couplings: list[TemporalCoupling]
    dropped_deleted_partners: int


def analyze_temporal_coupling(  # [3b] Find co-changing files
    commits: list[Commit],
    policy: CouplingPolicy,
    live_paths: frozenset[str] | None = None,
) -> CouplingAnalysis:
    """Detect files that change together frequently.

    ``commits`` must already exclude bulk commits (see ``exclude_bulk``), so
    every remaining file revision counts toward the denominators and no commit
    generates quadratic pairs. A pair is kept when its symmetric ratio, which
    equals the larger directional rate, reaches ``policy.min_ratio`` and it has
    at least ``policy.min_shared_revisions`` shared revisions. Pairs are
    ordered by the 95% Wilson lower bound of the symmetric ratio, then shared
    revisions, ratio, and paths, so repeated evidence outranks a perfect
    one-off.

    Args:
        commits: Non-bulk commit history.
        policy: Thresholds for including a pair.
        live_paths: Paths present at HEAD. When given, pairs with a side
            outside it are dropped and counted.

    Returns:
        Included pairs and the number dropped for a deleted side.
    """
    commit_counts: dict[str, int] = defaultdict(int)
    co_change_counts: dict[tuple[str, str], int] = defaultdict(int)

    for commit in commits:
        files = sorted({f.path for f in commit.files})
        for path in files:
            commit_counts[path] += 1
        for file_a, file_b in combinations(files, 2):
            co_change_counts[(file_a, file_b)] += 1

    included: list[TemporalCoupling] = []
    dropped_deleted_partners = 0
    for (file_a, file_b), co_changes in co_change_counts.items():
        coupling = TemporalCoupling(
            file_a=file_a,
            file_b=file_b,
            co_change_count=co_changes,
            commits_a=commit_counts[file_a],
            commits_b=commit_counts[file_b],
        )
        if (
            coupling.coupling_ratio < policy.min_ratio
            or coupling.co_change_count < policy.min_shared_revisions
        ):
            continue
        if live_paths is not None and not {file_a, file_b} <= live_paths:
            dropped_deleted_partners += 1
            continue
        included.append(coupling)

    included.sort(
        key=lambda coupling: (
            -coupling.confidence_lower_bound,
            -coupling.co_change_count,
            -coupling.coupling_ratio,
            coupling.file_a,
            coupling.file_b,
        )
    )
    return CouplingAnalysis(
        couplings=included,
        dropped_deleted_partners=dropped_deleted_partners,
    )


def couplings_by_file(
    couplings: list[TemporalCoupling], *, min_rate: float = 0.0
) -> dict[str, list[CouplingInfo]]:
    """Index pairs by each side, keeping partners whose rate_to_partner reaches min_rate.

    Each file's partners are sorted by ``coupling_info_sort_key``.
    """
    by_file: dict[str, list[CouplingInfo]] = defaultdict(list)
    for coupling in couplings:
        for path in (coupling.file_a, coupling.file_b):
            info = coupling_info_for(coupling, path)
            if info.rate_to_partner >= min_rate:
                by_file[path].append(info)
    for partners in by_file.values():
        partners.sort(key=coupling_info_sort_key)
    return dict(by_file)
