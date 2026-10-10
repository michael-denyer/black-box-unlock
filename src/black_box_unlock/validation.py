"""Self-validation: does the hotspot ranking predict where bugs get fixed?

Split-history design: pick a cutoff commit, rank the files that existed at that
commit using only history up to it, then count bug-fix commits after it. See
docs/VALIDATION.md.
"""

import math
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

from pydantic import BaseModel

from .complexity import indentation_complexity_text
from .core.exceptions import InsufficientHistoryError
from .git.churn import parse_history_entries
from .git.defects import bugfix_counts, is_bugfix_message
from .git.log import Commit, fetch_git_history
from .git.run import run_git

TOP_DECILE = 0.10


class MethodScore(BaseModel):
    """How one ranking method scored against post-cutoff bug-fix touches."""

    spearman: float | None
    top_decile_share: float | None
    top_files: list[str]


class ValidationReport(BaseModel):
    """Outcome of one split-history validation run (experiment artifact)."""

    repo: str
    days: int
    split: float
    cutoff: datetime
    cutoff_sha: str
    universe_size: int
    train_commits: int
    test_commits: int
    test_bugfix_commits: int
    test_bugfix_touches: int
    bugfix_coverage: float | None
    methods: dict[str, MethodScore]


class CutoffFile(BaseModel):
    """One file as it stood at the cutoff commit, with its train-half churn."""

    path: str
    commits: int
    complexity: float
    lines: int


def split_history(commits: list[Commit], cutoff: datetime) -> tuple[list[Commit], list[Commit]]:
    """Partition commits into (train, test) halves at the cutoff.

    Commits strictly before the cutoff form the train half; the rest form
    the test half.
    """
    train: list[Commit] = []
    test: list[Commit] = []
    for commit in commits:
        (train if commit.timestamp < cutoff else test).append(commit)
    return train, test


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


def score_ranking(scores: dict[str, float], touches: dict[str, int]) -> MethodScore:
    """Score one ranking against bug-fix touches over the same universe.

    `scores` maps every universe file to its rank score; higher ranks first,
    ties break on path so the result is deterministic.
    """
    universe = sorted(scores, key=lambda p: (-scores[p], p))
    hits = [touches.get(p, 0) for p in universe]
    total = sum(hits)
    top_k = math.ceil(len(universe) * TOP_DECILE)
    return MethodScore(
        spearman=spearman_rho([scores[p] for p in universe], [float(h) for h in hits]),
        top_decile_share=sum(hits[:top_k]) / total if total else None,
        top_files=universe[:top_k],
    )


def _pct(value: float | None) -> str:
    return f"{value:.0%}" if value is not None else "n/a"


def _rho(value: float | None) -> str:
    return f"{value:.2f}" if value is not None else "n/a"


def render_report(report: ValidationReport) -> str:
    """One text block per repo: header line, then one line per ranking method."""
    lines = [
        f"{report.repo} @ {report.cutoff_sha[:7]} ({report.cutoff:%Y-%m-%d}): "
        f"universe={report.universe_size} files, "
        f"{report.test_bugfix_commits} bug-fix commits after the cutoff, "
        f"{report.test_bugfix_touches} touches on the universe "
        f"(coverage {_pct(report.bugfix_coverage)})"
    ]
    for name, score in report.methods.items():
        lines.append(
            f"  {name:<8} rho={_rho(score.spearman)}  top-10% share={_pct(score.top_decile_share)}"
        )
    return "\n".join(lines)


def _cutoff_commit(repo_path: Path, cutoff: datetime) -> str | None:
    """Latest first-parent commit committed before the cutoff, or None."""
    output = run_git(
        repo_path,
        ["rev-list", "-1", "--first-parent", f"--before={cutoff.isoformat()}", "HEAD"],
        tolerate_unborn=True,
    )
    return output.strip() or None


def _tree_contents(repo_path: Path, sha: str, paths: list[str]) -> dict[str, str]:
    """Read each path's content at `sha`; paths absent from that tree are omitted."""
    if not paths:
        return {}
    result = subprocess.run(
        ["git", "-c", "core.quotePath=false", "-C", str(repo_path), "cat-file", "--batch"],
        input="".join(f"{sha}:{path}\n" for path in paths).encode(),
        capture_output=True,
        check=True,
    )
    output = result.stdout
    contents: dict[str, str] = {}
    pos = 0
    for path in paths:
        newline = output.index(b"\n", pos)
        header = output[pos:newline].decode(errors="ignore")
        pos = newline + 1
        if header.endswith(" missing"):
            continue
        size = int(header.rsplit(" ", 1)[1])
        contents[path] = output[pos : pos + size].decode(errors="ignore")
        pos += size + 1
    return contents


def cutoff_universe(repo_path: Path, cutoff_sha: str, train: list[Commit]) -> list[CutoffFile]:
    """Files churned in the train half that exist in the cutoff tree.

    Complexity and length come from each file's content at the cutoff, so the
    ranking only sees information that existed at the cutoff.
    """
    churn = {entry.path: entry.commits for entry in parse_history_entries(train)}
    contents = _tree_contents(repo_path, cutoff_sha, sorted(churn))
    return [
        CutoffFile(
            path=path,
            commits=churn[path],
            complexity=indentation_complexity_text(Path(path), text),
            lines=len(text.splitlines()),
        )
        for path, text in contents.items()
    ]


def validate_repo(repo_path: Path, days: int = 730, split: float = 0.5) -> ValidationReport:
    """Validate the hotspot ranking against subsequent bug-fix commits.

    Ranks the cutoff universe by hotspot score (train-half commits x
    indentation complexity at the cutoff, the shipped formula) and scores it
    against bug-fix commits after the cutoff.

    Raises:
        InsufficientHistoryError: If either half contains no commits, or no
            train-half file exists in the cutoff tree.
    """
    history = fetch_git_history(repo_path, days)
    cutoff = datetime.now(timezone.utc) - timedelta(days=days * (1 - split))
    train, test = split_history(history, cutoff)
    cutoff_sha = _cutoff_commit(repo_path, cutoff)
    if not train or not test or cutoff_sha is None:
        raise InsufficientHistoryError(
            f"Need commits on both sides of {cutoff:%Y-%m-%d} "
            f"(train: {len(train)}, test: {len(test)}); "
            "adjust --days/--split so the cutoff falls inside the repo's history"
        )

    universe = cutoff_universe(repo_path, cutoff_sha, train)
    if not universe:
        raise InsufficientHistoryError("No train-half file exists in the cutoff tree")

    test_counts = bugfix_counts(test)
    universe_paths = {f.path for f in universe}
    touches = {p: n for p, n in test_counts.items() if p in universe_paths}
    universe_touches = sum(touches.values())
    total_touches = sum(test_counts.values())

    return ValidationReport(
        repo=repo_path.resolve().name,
        days=days,
        split=split,
        cutoff=cutoff,
        cutoff_sha=cutoff_sha,
        universe_size=len(universe),
        train_commits=len(train),
        test_commits=len(test),
        test_bugfix_commits=sum(1 for c in test if is_bugfix_message(c.message)),
        test_bugfix_touches=universe_touches,
        bugfix_coverage=universe_touches / total_touches if total_touches else None,
        methods={
            "hotspot": score_ranking({f.path: f.commits * f.complexity for f in universe}, touches),
        },
    )
