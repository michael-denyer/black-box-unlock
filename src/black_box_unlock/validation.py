"""Self-validation: does the hotspot ranking predict where bugs get fixed?

Split-history design: rank files by hotspot score computed from an older window,
count bug-fix commits in the newer window, correlate. See docs/VALIDATION.md.
"""

import math
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from .complexity import indentation_complexity
from .core.exceptions import InsufficientHistoryError
from .git.churn import parse_history_entries
from .git.defects import bugfix_counts
from .git.log import fetch_git_history

TOP_DECILE = 0.10


class ValidationResult(BaseModel):
    """Outcome of one split-history validation run (experiment artifact)."""

    repo: str
    days: int
    split: float
    cutoff: datetime
    file_count: int
    spearman: float | None
    top_decile_share: float | None
    bugfix_coverage: float | None
    test_bugfix_touches: int


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


def validate_repo(repo_path: Path, days: int = 730, split: float = 0.5) -> ValidationResult:
    """Validate the hotspot ranking against subsequent bug-fix commits.

    Ranks files by hotspot score (train-half commits x current indentation
    complexity — the shipped formula) and counts test-half bug-fix commits
    per file. The universe is files churned in the train half that still
    exist on disk.

    Raises:
        InsufficientHistoryError: If either half contains no commits, or no
            ranked file still exists on disk.
    """
    history = fetch_git_history(repo_path, days)
    cutoff = datetime.now(timezone.utc) - timedelta(days=days * (1 - split))
    train, test = split_history(history, cutoff)
    if not train["entries"] or not test["entries"]:
        raise InsufficientHistoryError(
            f"Need commits on both sides of {cutoff:%Y-%m-%d} "
            f"(train: {len(train['entries'])}, test: {len(test['entries'])}); "
            "adjust --days/--split so the cutoff falls inside the repo's history"
        )

    scores: dict[str, float] = {}
    for churn in parse_history_entries(train):
        full_path = repo_path / churn.path
        if full_path.exists():  # the shipped ranking only covers existing files
            scores[churn.path] = churn.commits * indentation_complexity(full_path)
    if not scores:
        raise InsufficientHistoryError("No train-half file still exists on disk")

    test_counts = bugfix_counts(test)
    universe = sorted(scores, key=lambda p: (-scores[p], p))  # deterministic tiebreak
    touches = [test_counts.get(p, 0) for p in universe]

    universe_touches = sum(touches)
    top_k = math.ceil(len(universe) * TOP_DECILE)
    top_decile_share = sum(touches[:top_k]) / universe_touches if universe_touches else None
    total_touches = sum(test_counts.values())
    coverage = universe_touches / total_touches if total_touches else None

    return ValidationResult(
        repo=repo_path.resolve().name,
        days=days,
        split=split,
        cutoff=cutoff,
        file_count=len(universe),
        spearman=spearman_rho([scores[p] for p in universe], [float(t) for t in touches]),
        top_decile_share=top_decile_share,
        bugfix_coverage=coverage,
        test_bugfix_touches=universe_touches,
    )
