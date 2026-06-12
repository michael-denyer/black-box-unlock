"""Self-validation: does the hotspot ranking predict where bugs get fixed?

Split-history design: rank files by hotspot score computed from an older window,
count bug-fix commits in the newer window, correlate. See docs/VALIDATION.md.
"""

from datetime import datetime
from typing import Any


def split_history(
    history: dict[str, Any], cutoff: datetime
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Partition history entries into (train, test) halves at the cutoff.

    Entries strictly before the cutoff form the train half; the rest form
    the test half. Accepts both +00:00 offsets (git %aI) and Z suffixes.
    """
    train: list[dict[str, Any]] = []
    test: list[dict[str, Any]] = []
    for entry in history.get("entries", []):
        # Python 3.10's fromisoformat rejects the Z suffix
        timestamp = datetime.fromisoformat(entry["timestamp"].replace("Z", "+00:00"))
        (train if timestamp < cutoff else test).append(entry)
    return {"entries": train}, {"entries": test}


def _average_ranks(values: list[float]) -> list[float]:
    """1-based ranks, ties receive the average of their positions."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        average = (i + j) / 2 + 1
        for k in range(i, j + 1):
            ranks[order[k]] = average
        i = j + 1
    return ranks


def spearman_rho(xs: list[float], ys: list[float]) -> float | None:
    """Spearman rank correlation with average ranks for ties.

    Returns:
        Correlation in [-1, 1], or None when undefined (fewer than two
        points, or zero variance in either ranking).
    """
    n = len(xs)
    if n < 2:
        return None
    rx, ry = _average_ranks(xs), _average_ranks(ys)
    mean_x, mean_y = sum(rx) / n, sum(ry) / n
    cov = sum((a - mean_x) * (b - mean_y) for a, b in zip(rx, ry, strict=False))
    var_x = sum((a - mean_x) ** 2 for a in rx)
    var_y = sum((b - mean_y) ** 2 for b in ry)
    if var_x == 0 or var_y == 0:
        return None
    return cov / (var_x * var_y) ** 0.5
