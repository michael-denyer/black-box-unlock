"""Self-validation: does the hotspot ranking predict where bugs get fixed?

Split-history design: pick a cutoff commit, rank the files that existed at that
commit using only history up to it, then count bug-fix commits after it. See
docs/VALIDATION.md.
"""

import math
import random
import statistics
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

from pydantic import BaseModel

from .complexity import indentation_complexity_text
from .config import resolve_coupling_policy
from .core.exceptions import BlackBoxUnlockError, GitToolNotFoundError, InsufficientHistoryError
from .git.churn import parse_history_entries
from .git.defects import bugfix_counts, is_bugfix_message
from .git.log import Clock, Commit, exclude_bulk, fetch_git_history
from .git.run import run_git

TOP_DECILE = 0.10
# The committer date orders history and is what `git log --since` filters on,
# so the window, the split, and the cutoff commit all read the same clock.
CLOCK: Clock = "committer"
RANDOM_DRAWS = 200
RANDOM_SEED = 20260612
# Below either floor the percentages are noise: with few files the top decile
# is one or two files, and with few fixes one commit swings the share.
MIN_UNIVERSE_FILES = 20
MIN_TEST_BUGFIX_COMMITS = 30


class MethodScore(BaseModel):
    """How one ranking method scored against post-cutoff bug-fix touches."""

    spearman: float | None
    top_decile_share: float | None
    top_files: list[str]


class RandomBaseline(BaseModel):
    """Score distribution of `draws` seeded random rankings of the same universe."""

    draws: int
    seed: int
    spearman_mean: float | None
    spearman_sd: float | None
    top_decile_share_mean: float | None
    top_decile_share_sd: float | None


class ValidationReport(BaseModel):
    """Outcome of one split-history validation run (experiment artifact)."""

    repo: str
    days: int
    split: float
    cutoff: datetime
    cutoff_sha: str
    clock: Clock
    universe_size: int
    train_commits: int
    test_commits: int
    test_bugfix_commits: int
    test_bugfix_touches: int
    bugfix_coverage: float | None
    methods: dict[str, MethodScore]
    random: RandomBaseline
    p_value: float | None
    insufficient_data: bool
    insufficient_reasons: list[str]


class CutoffFile(BaseModel):
    """One file as it stood at the cutoff commit, with its train-half churn."""

    path: str
    commits: int
    complexity: float
    lines: int


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


def _top_hits(universe: list[str], hits: list[int], scores: dict[str, float], top_k: int) -> float:
    """Touches credited to the top `top_k` slots.

    Files tied at the boundary score share the slots they compete for pro
    rata, so a tie is not decided by path order.
    """
    boundary = scores[universe[top_k - 1]]
    above = [h for p, h in zip(universe, hits, strict=True) if scores[p] > boundary]
    tied = [h for p, h in zip(universe, hits, strict=True) if scores[p] == boundary]
    need = top_k - len(above)
    return sum(above) + need * sum(tied) / len(tied)


def score_ranking(scores: dict[str, float], touches: dict[str, int]) -> MethodScore:
    """Score one ranking against bug-fix touches over the same universe.

    `scores` maps every universe file to its rank score; higher ranks first.
    `top_files` lists the top slots with ties broken on path so it is
    deterministic; `top_decile_share` gives boundary ties fractional credit.
    """
    universe = sorted(scores, key=lambda p: (-scores[p], p))
    hits = [touches.get(p, 0) for p in universe]
    total = sum(hits)
    top_k = math.ceil(len(universe) * TOP_DECILE)
    return MethodScore(
        spearman=spearman_rho([scores[p] for p in universe], [float(h) for h in hits]),
        top_decile_share=_top_hits(universe, hits, scores, top_k) / total if total else None,
        top_files=universe[:top_k],
    )


def _mean_sd(values: list[float]) -> tuple[float | None, float | None]:
    if not values:
        return None, None
    mean = statistics.fmean(values)
    sd = statistics.pstdev(values) if len(values) > 1 else 0.0
    return mean, sd


def random_draws(
    paths: list[str], touches: dict[str, int], draws: int = RANDOM_DRAWS, seed: int = RANDOM_SEED
) -> list[MethodScore]:
    """Score `draws` uniformly random rankings of `paths` with the shared metric."""
    rng = random.Random(seed)
    order = list(paths)
    scored = []
    for _ in range(draws):
        rng.shuffle(order)
        scored.append(score_ranking({p: float(-i) for i, p in enumerate(order)}, touches))
    return scored


def summarize_random(draws: list[MethodScore], seed: int = RANDOM_SEED) -> RandomBaseline:
    """Collapse scored random draws into mean and sd per metric."""
    rho_mean, rho_sd = _mean_sd([d.spearman for d in draws if d.spearman is not None])
    share_mean, share_sd = _mean_sd(
        [d.top_decile_share for d in draws if d.top_decile_share is not None]
    )
    return RandomBaseline(
        draws=len(draws),
        seed=seed,
        spearman_mean=rho_mean,
        spearman_sd=rho_sd,
        top_decile_share_mean=share_mean,
        top_decile_share_sd=share_sd,
    )


def permutation_p(observed: float | None, draws: list[float]) -> float | None:
    """One-sided permutation p: share of random draws scoring at least `observed`.

    Uses the (b + 1) / (K + 1) estimator, so K draws can never report 0.
    """
    if observed is None or not draws:
        return None
    at_or_above = sum(1 for d in draws if d >= observed)
    return (at_or_above + 1) / (len(draws) + 1)


def insufficiency_reasons(universe_size: int, test_bugfix_commits: int) -> list[str]:
    """Which sample floors the run falls below; empty when the figures are usable."""
    reasons = []
    if universe_size < MIN_UNIVERSE_FILES:
        reasons.append(f"{universe_size} universe files < {MIN_UNIVERSE_FILES}")
    if test_bugfix_commits < MIN_TEST_BUGFIX_COMMITS:
        reasons.append(
            f"{test_bugfix_commits} post-cutoff bug-fix commits < {MIN_TEST_BUGFIX_COMMITS}"
        )
    return reasons


def _pct(value: float | None) -> str:
    return f"{value:.0%}" if value is not None else "n/a"


def _rho(value: float | None) -> str:
    return f"{value:.2f}" if value is not None else "n/a"


def render_report(report: ValidationReport) -> str:
    """One text block per repo: header line, then one line per ranking method."""
    header = (
        f"{report.repo} @ {report.cutoff_sha[:7]} ({report.cutoff:%Y-%m-%d}): "
        f"universe={report.universe_size} files, "
        f"{report.test_bugfix_commits} bug-fix commits after the cutoff, "
        f"{report.test_bugfix_touches} touches on the universe"
    )
    if report.insufficient_data:
        return "\n".join([header, "  insufficient data: " + "; ".join(report.insufficient_reasons)])
    lines = [f"{header} (coverage {_pct(report.bugfix_coverage)})"]
    for name, score in report.methods.items():
        lines.append(
            f"  {name:<8} rho={_rho(score.spearman)}  top-10% share={_pct(score.top_decile_share)}"
        )
    rnd = report.random
    sd = f" (sd {rnd.top_decile_share_sd:.0%})" if rnd.top_decile_share_sd is not None else ""
    lines.append(
        f"  {'random':<8} rho={_rho(rnd.spearman_mean)}  "
        f"top-10% share={_pct(rnd.top_decile_share_mean)}{sd}  "
        f"mean of {rnd.draws} draws, seed {rnd.seed}"
    )
    lines.append(f"  hotspot share vs random: one-sided permutation {_p_label(report)}")
    return "\n".join(lines)


def _p_label(report: ValidationReport) -> str:
    """`p=0.025`, or a bound when no draw reached the observed share."""
    if report.p_value is None:
        return "p=n/a"
    floor = 1 / (report.random.draws + 1)
    if report.p_value <= floor:
        return f"p<{floor:.3f} (no draw reached it)"
    return f"p={report.p_value:.3f}"


def _cutoff_commit(repo_path: Path, cutoff: datetime) -> str | None:
    """Latest first-parent commit committed before the cutoff, or None."""
    output = run_git(
        repo_path,
        ["rev-list", "-1", "--first-parent", f"--before={cutoff.isoformat()}", "HEAD"],
        tolerate_unborn=True,
    )
    return output.strip() or None


def _tree_contents(repo_path: Path, sha: str, paths: list[str]) -> dict[str, str]:
    """Read each path's blob at `sha`.

    Paths absent from that tree, or naming a tree (a file later replaced by a
    directory), are omitted. Bytes in and out, so this cannot go through
    `run_git`, but it maps errors the same way.

    Raises:
        GitToolNotFoundError: If the git binary is not installed.
        BlackBoxUnlockError: If `git cat-file` fails.
    """
    if not paths:
        return {}
    try:
        result = subprocess.run(
            ["git", "-c", "core.quotePath=false", "-C", str(repo_path), "cat-file", "--batch"],
            input="".join(f"{sha}:{path}\n" for path in paths).encode(),
            capture_output=True,
            check=True,
        )
    except FileNotFoundError as e:
        raise GitToolNotFoundError("git not found on PATH") from e
    except subprocess.CalledProcessError as e:
        raise BlackBoxUnlockError(f"git cat-file failed: {e.stderr.decode(errors='ignore')}") from e
    output = result.stdout
    contents: dict[str, str] = {}
    pos = 0
    for path in paths:
        newline = output.index(b"\n", pos)
        header = output[pos:newline].decode(errors="ignore")
        pos = newline + 1
        if header.endswith(" missing"):
            continue
        kind, size = header.split(" ")[1:]
        if kind == "blob":
            contents[path] = output[pos : pos + int(size)].decode(errors="ignore")
        pos += int(size) + 1
    return contents


def _touches_by_cutoff_name(
    test_counts: dict[str, int], test: list[Commit], universe_paths: set[str]
) -> dict[str, int]:
    """Attribute test-half touches to the name each file had at the cutoff.

    Test-half paths are the names at HEAD. A file renamed after the cutoff is
    in the universe under its old name, which its commits record in
    ``former_paths``.
    """
    former: dict[str, list[str]] = {}
    for commit in test:
        for file in commit.files:
            former.setdefault(file.path, []).extend(file.former_paths)
    touches: dict[str, int] = {}
    for path, count in test_counts.items():
        for name in (path, *former.get(path, [])):
            if name in universe_paths:
                touches[name] = touches.get(name, 0) + count
                break
    return touches


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

    The halves are split by ancestry, not by timestamp: train is every
    windowed commit reachable from the cutoff commit, test is everything
    reachable from HEAD but not from the cutoff commit. A side-branch commit
    merged after the cutoff is therefore test, matching the cutoff tree.

    Raises:
        InsufficientHistoryError: If either half contains no commits, or no
            train-half file exists in the cutoff tree.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=days * (1 - split))
    cutoff_sha = _cutoff_commit(repo_path, cutoff)
    no_history = (
        f"Need commits on both sides of {cutoff:%Y-%m-%d}; "
        "adjust --days/--split so the cutoff falls inside the repo's history"
    )
    if cutoff_sha is None:
        raise InsufficientHistoryError(no_history)
    max_changeset_size = resolve_coupling_policy(repo_path).max_changeset_size
    train, _ = exclude_bulk(
        fetch_git_history(repo_path, days, cutoff_sha, clock=CLOCK), max_changeset_size
    )
    test, _ = exclude_bulk(
        fetch_git_history(repo_path, days, f"{cutoff_sha}..HEAD", clock=CLOCK),
        max_changeset_size,
    )
    if not train or not test:
        raise InsufficientHistoryError(f"{no_history} (train: {len(train)}, test: {len(test)})")

    universe = cutoff_universe(repo_path, cutoff_sha, train)
    if not universe:
        raise InsufficientHistoryError("No train-half file exists in the cutoff tree")

    universe_paths = {f.path for f in universe}
    test_counts = bugfix_counts(test)
    touches = _touches_by_cutoff_name(test_counts, test, universe_paths)
    universe_touches = sum(touches.values())
    total_touches = sum(test_counts.values())
    methods = {
        "hotspot": score_ranking({f.path: f.commits * f.complexity for f in universe}, touches),
        "churn": score_ranking({f.path: float(f.commits) for f in universe}, touches),
        "length": score_ranking({f.path: float(f.lines) for f in universe}, touches),
    }
    draws = random_draws(sorted(universe_paths), touches)
    # Merge commits carry no files and often a fix-named branch in the subject;
    # the fix they merge is already counted, so only commits with files count.
    test_bugfix_commits = sum(1 for c in test if c.files and is_bugfix_message(c.message))
    reasons = insufficiency_reasons(len(universe), test_bugfix_commits)

    return ValidationReport(
        repo=repo_path.resolve().name,
        days=days,
        split=split,
        cutoff=cutoff,
        cutoff_sha=cutoff_sha,
        clock=CLOCK,
        universe_size=len(universe),
        train_commits=len(train),
        test_commits=len(test),
        test_bugfix_commits=test_bugfix_commits,
        test_bugfix_touches=universe_touches,
        bugfix_coverage=universe_touches / total_touches if total_touches else None,
        methods=methods,
        random=summarize_random(draws),
        p_value=permutation_p(
            methods["hotspot"].top_decile_share,
            [d.top_decile_share for d in draws if d.top_decile_share is not None],
        ),
        insufficient_data=bool(reasons),
        insufficient_reasons=reasons,
    )
