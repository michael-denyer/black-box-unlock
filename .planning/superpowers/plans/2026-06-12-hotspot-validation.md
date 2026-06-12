# Hotspot-vs-Bugfix Self-Validation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `bbu validate` — split-history validation that measures whether hotspot ranking predicts subsequent bug-fix commits — run it on real repos, publish the numbers in the README (BBU-6352).

**Architecture:** New `validation.py` module: fetch git history once, split at a cutoff, rank files by hotspot score from the older half, count bug-fix commits in the newer half, report Spearman rho + top-decile bug-fix share + coverage. Spec: `.planning/superpowers/specs/2026-06-12-hotspot-validation-design.md`.

**Tech Stack:** Python 3.10+, pydantic, typer, pytest. No new dependencies — Spearman implemented by hand.

---

### Task 1: `spearman_rho`

**Files:**
- Create: `src/black_box_unlock/validation.py`
- Test: `tests/unit/test_validation.py`

- [ ] **Step 1: Write the failing tests**

```python
"""Unit tests for hotspot-vs-bugfix self-validation."""

import pytest

from black_box_unlock.validation import spearman_rho


class TestSpearmanRho:
    def test_perfect_monotonic_is_one(self):
        assert spearman_rho([1, 2, 3, 4], [10, 20, 30, 40]) == pytest.approx(1.0)

    def test_perfect_inverse_is_minus_one(self):
        assert spearman_rho([1, 2, 3, 4], [40, 30, 20, 10]) == pytest.approx(-1.0)

    def test_nonlinear_monotonic_is_still_one(self):
        # rank correlation ignores scale: x vs x**3 is perfectly monotonic
        assert spearman_rho([1, 2, 3, 4], [1, 8, 27, 64]) == pytest.approx(1.0)

    def test_ties_use_average_ranks(self):
        # ys has a tie; scipy.stats.spearmanr gives 0.9486832980505138 here
        rho = spearman_rho([1, 2, 3, 4], [10, 20, 20, 30])
        assert rho == pytest.approx(0.9486832980505138)

    def test_constant_input_returns_none(self):
        assert spearman_rho([1, 2, 3], [5, 5, 5]) is None

    def test_fewer_than_two_points_returns_none(self):
        assert spearman_rho([1], [2]) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_validation.py -v -p no:randomly --no-cov`
Expected: FAIL with `ModuleNotFoundError` / `ImportError` (validation module does not exist)

- [ ] **Step 3: Write the implementation**

```python
"""Self-validation: does the hotspot ranking predict where bugs get fixed?

Split-history design: rank files by hotspot score computed from an older window,
count bug-fix commits in the newer window, correlate. See docs/VALIDATION.md.
"""


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
    cov = sum((a - mean_x) * (b - mean_y) for a, b in zip(rx, ry))
    var_x = sum((a - mean_x) ** 2 for a in rx)
    var_y = sum((b - mean_y) ** 2 for b in ry)
    if var_x == 0 or var_y == 0:
        return None
    return cov / (var_x * var_y) ** 0.5
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_validation.py -v -p no:randomly --no-cov`
Expected: 6 PASS

- [ ] **Step 5: Commit**

```bash
git add tests/unit/test_validation.py src/black_box_unlock/validation.py
git commit -m "feat(validation): Spearman rank correlation with tie handling"
```

---

### Task 2: `split_history`

**Files:**
- Modify: `src/black_box_unlock/validation.py`
- Test: `tests/unit/test_validation.py`

- [ ] **Step 1: Write the failing tests** (append to `tests/unit/test_validation.py`)

```python
from datetime import datetime, timezone

from black_box_unlock.validation import split_history


def _entry(timestamp: str, message: str = "feat: x", paths: list[str] | None = None) -> dict:
    return {
        "timestamp": timestamp,
        "author_email": "a@x.com",
        "message": message,
        "files": [{"path": p, "added_lines": 1, "deleted_lines": 0} for p in (paths or ["a.py"])],
    }


class TestSplitHistory:
    CUTOFF = datetime(2026, 3, 1, tzinfo=timezone.utc)

    def test_partitions_entries_at_cutoff(self):
        history = {
            "entries": [
                _entry("2026-05-01T10:00:00+00:00"),
                _entry("2026-01-01T10:00:00+00:00"),
            ]
        }
        train, test = split_history(history, self.CUTOFF)
        assert [e["timestamp"] for e in train["entries"]] == ["2026-01-01T10:00:00+00:00"]
        assert [e["timestamp"] for e in test["entries"]] == ["2026-05-01T10:00:00+00:00"]

    def test_entry_exactly_at_cutoff_goes_to_test(self):
        history = {"entries": [_entry("2026-03-01T00:00:00+00:00")]}
        train, test = split_history(history, self.CUTOFF)
        assert train["entries"] == []
        assert len(test["entries"]) == 1

    def test_zulu_suffix_timestamps_parse(self):
        # git %aI emits +00:00 offsets but fixtures and other tools use Z
        history = {"entries": [_entry("2026-01-01T10:00:00Z")]}
        train, test = split_history(history, self.CUTOFF)
        assert len(train["entries"]) == 1

    def test_empty_history(self):
        train, test = split_history({"entries": []}, self.CUTOFF)
        assert train["entries"] == [] and test["entries"] == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_validation.py -v -p no:randomly --no-cov`
Expected: new tests FAIL with ImportError (`split_history` not defined)

- [ ] **Step 3: Write the implementation** (append to `validation.py`; add imports at top)

```python
from datetime import datetime
from typing import Any


def split_history(history: dict[str, Any], cutoff: datetime) -> tuple[dict[str, Any], dict[str, Any]]:
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_validation.py -v -p no:randomly --no-cov`
Expected: 10 PASS

- [ ] **Step 5: Commit**

```bash
git add tests/unit/test_validation.py src/black_box_unlock/validation.py
git commit -m "feat(validation): split git history at a cutoff timestamp"
```

---

### Task 3: `validate_repo` + `ValidationResult` + `InsufficientHistoryError`

**Files:**
- Modify: `src/black_box_unlock/validation.py`
- Modify: `src/black_box_unlock/core/exceptions.py`
- Test: `tests/unit/test_validation.py`

- [ ] **Step 1: Write the failing tests** (append to `tests/unit/test_validation.py`)

```python
from pathlib import Path
from unittest.mock import patch

from black_box_unlock.core.exceptions import InsufficientHistoryError
from black_box_unlock.validation import validate_repo

INDENTED = "def f(x):\n    if x:\n        return 1\n    return 0\n"
FLAT = "X = 1\nY = 2\n"


def _days_ago(n: int) -> str:
    from datetime import datetime, timedelta, timezone

    return (datetime.now(timezone.utc) - timedelta(days=n)).isoformat()


def _fake_history() -> dict:
    # Train half (older than the 50-day cutoff for days=100, split=0.5):
    # hot.py churns 3x, cold.py once. Test half: 2 bugfix commits touch hot.py.
    return {
        "entries": [
            _entry(_days_ago(90), "feat: a", ["hot.py"]),
            _entry(_days_ago(80), "feat: b", ["hot.py", "cold.py"]),
            _entry(_days_ago(70), "feat: c", ["hot.py", "gone.py"]),
            _entry(_days_ago(30), "fix: crash", ["hot.py"]),
            _entry(_days_ago(10), "fix: regression", ["hot.py"]),
        ]
    }


class TestValidateRepo:
    def _run(self, tmp_path: Path):
        (tmp_path / "hot.py").write_text(INDENTED)
        (tmp_path / "cold.py").write_text(FLAT)
        # gone.py intentionally absent: deleted files drop out of the universe
        with patch("black_box_unlock.validation.fetch_git_history") as mock_fetch:
            mock_fetch.return_value = _fake_history()
            return validate_repo(tmp_path, days=100, split=0.5)

    def test_correlates_train_hotspots_with_test_bugfixes(self, tmp_path):
        result = self._run(tmp_path)
        assert result.spearman == pytest.approx(1.0)  # hot.py: top score, all fixes

    def test_universe_excludes_deleted_files(self, tmp_path):
        result = self._run(tmp_path)
        assert result.file_count == 2  # hot.py, cold.py — not gone.py

    def test_top_decile_share_counts_bugfix_touches(self, tmp_path):
        # universe of 2 -> top decile is ceil(0.2)=1 file (hot.py) with all touches
        result = self._run(tmp_path)
        assert result.top_decile_share == pytest.approx(1.0)
        assert result.test_bugfix_touches == 2

    def test_coverage_is_full_when_all_fixes_hit_ranked_files(self, tmp_path):
        result = self._run(tmp_path)
        assert result.bugfix_coverage == pytest.approx(1.0)

    def test_no_test_window_bugfixes_yields_none_share(self, tmp_path):
        (tmp_path / "hot.py").write_text(INDENTED)
        history = {
            "entries": [
                _entry(_days_ago(90), "feat: a", ["hot.py"]),
                _entry(_days_ago(10), "feat: quiet period", ["hot.py"]),
            ]
        }
        with patch("black_box_unlock.validation.fetch_git_history") as mock_fetch:
            mock_fetch.return_value = history
            result = validate_repo(tmp_path, days=100, split=0.5)
        assert result.top_decile_share is None
        assert result.bugfix_coverage is None

    def test_empty_train_half_raises(self, tmp_path):
        (tmp_path / "hot.py").write_text(INDENTED)
        history = {"entries": [_entry(_days_ago(10), "feat: a", ["hot.py"])]}
        with patch("black_box_unlock.validation.fetch_git_history") as mock_fetch:
            mock_fetch.return_value = history
            with pytest.raises(InsufficientHistoryError):
                validate_repo(tmp_path, days=100, split=0.5)

    def test_empty_test_half_raises(self, tmp_path):
        (tmp_path / "hot.py").write_text(INDENTED)
        history = {"entries": [_entry(_days_ago(90), "feat: a", ["hot.py"])]}
        with patch("black_box_unlock.validation.fetch_git_history") as mock_fetch:
            mock_fetch.return_value = history
            with pytest.raises(InsufficientHistoryError):
                validate_repo(tmp_path, days=100, split=0.5)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_validation.py -v -p no:randomly --no-cov`
Expected: new tests FAIL with ImportError (`InsufficientHistoryError`, `validate_repo` not defined)

- [ ] **Step 3: Add the exception** (append to `src/black_box_unlock/core/exceptions.py`)

```python
class InsufficientHistoryError(BlackBoxUnlockError):
    """Raised when a validation window contains no commits."""
```

- [ ] **Step 4: Write the implementation** (append to `validation.py`; extend imports)

```python
import math
from datetime import timedelta, timezone
from pathlib import Path

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
            "try a larger --days"
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
        spearman=spearman_rho([scores[p] for p in universe], touches),
        top_decile_share=top_decile_share,
        bugfix_coverage=coverage,
        test_bugfix_touches=universe_touches,
    )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_validation.py -v -p no:randomly --no-cov`
Expected: 17 PASS

- [ ] **Step 6: Commit**

```bash
git add tests/unit/test_validation.py src/black_box_unlock/validation.py src/black_box_unlock/core/exceptions.py
git commit -m "feat(validation): split-history hotspot-vs-bugfix validation"
```

---

### Task 4: `bbu validate` CLI command

**Files:**
- Modify: `src/black_box_unlock/cli.py` (after `coupling_guard`, before `version`)
- Test: `tests/unit/test_cli.py`

- [ ] **Step 1: Write the failing tests** (append to `tests/unit/test_cli.py`)

```python
from datetime import datetime, timezone

from black_box_unlock.core.exceptions import InsufficientHistoryError
from black_box_unlock.validation import ValidationResult


def _validation_result(repo: str = "demo", spearman: float | None = 0.62) -> ValidationResult:
    return ValidationResult(
        repo=repo,
        days=730,
        split=0.5,
        cutoff=datetime(2025, 6, 12, tzinfo=timezone.utc),
        file_count=120,
        spearman=spearman,
        top_decile_share=0.45,
        bugfix_coverage=0.88,
        test_bugfix_touches=200,
    )


class TestValidateCommand:
    def test_prints_rho_per_repo(self):
        with patch("black_box_unlock.validation.validate_repo") as mock_validate:
            mock_validate.return_value = _validation_result()
            result = runner.invoke(app, ["validate", "--repo", "."])
        assert result.exit_code == 0
        assert "0.62" in result.stdout

    def test_json_output(self):
        with patch("black_box_unlock.validation.validate_repo") as mock_validate:
            mock_validate.return_value = _validation_result()
            result = runner.invoke(app, ["validate", "--repo", ".", "--json"])
        assert result.exit_code == 0
        parsed = json.loads(result.stdout)
        assert parsed[0]["spearman"] == 0.62

    def test_median_rho_for_multiple_repos(self):
        results = [_validation_result("a", 0.4), _validation_result("b", 0.6), _validation_result("c", 0.8)]
        with patch("black_box_unlock.validation.validate_repo") as mock_validate:
            mock_validate.side_effect = results
            result = runner.invoke(app, ["validate", "--repo", "a", "--repo", "b", "--repo", "c"])
        assert result.exit_code == 0
        assert "median" in result.stdout.lower()
        assert "0.60" in result.stdout

    def test_failing_repo_reports_error_but_others_continue(self):
        with patch("black_box_unlock.validation.validate_repo") as mock_validate:
            mock_validate.side_effect = [InsufficientHistoryError("too little history"), _validation_result()]
            result = runner.invoke(app, ["validate", "--repo", "bad", "--repo", "good"])
        assert result.exit_code == 0
        assert "too little history" in result.stdout

    def test_all_repos_failing_exits_nonzero(self):
        with patch("black_box_unlock.validation.validate_repo") as mock_validate:
            mock_validate.side_effect = InsufficientHistoryError("too little history")
            result = runner.invoke(app, ["validate", "--repo", "bad"])
        assert result.exit_code == 1
```

`json` is already imported at the top of `test_cli.py`? Check — if not, add `import json` to the test file imports.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_cli.py -v -p no:randomly --no-cov -k Validate`
Expected: FAIL — `validate` is not a CLI command yet (usage error, exit code 2)

- [ ] **Step 3: Write the implementation** (insert in `cli.py` between `coupling_guard` and `version`)

```python
@app.command()
def validate(
    repos: list[Path] = typer.Option(
        [Path(".")], "--repo", help="Repository to validate (repeatable)"
    ),
    days: int = typer.Option(730, help="Total days of history (train + test halves)"),
    split: float = typer.Option(0.5, help="Fraction of the window forming the train half"),
    json_output: bool = typer.Option(False, "--json", help="Emit results as JSON"),
) -> None:
    """Validate the hotspot ranking against subsequent bug-fix commits.

    Splits history at a cutoff: files are ranked by hotspot score from the
    older half, then scored against bug-fix commits in the newer half.
    """
    import statistics

    from black_box_unlock import validation

    results = []
    for repo in repos:
        try:
            results.append(validation.validate_repo(repo, days=days, split=split))
        except BlackBoxUnlockError as e:
            console.print(f"[red]Error:[/red] {repo}: {e}")
    if json_output:
        print(json.dumps([r.model_dump(mode="json") for r in results], indent=2))
    else:
        for r in results:
            rho = f"{r.spearman:.2f}" if r.spearman is not None else "n/a"
            share = (
                f"{r.top_decile_share:.0%}" if r.top_decile_share is not None else "n/a"
            )
            coverage = (
                f"{r.bugfix_coverage:.0%}" if r.bugfix_coverage is not None else "n/a"
            )
            console.print(
                f"{r.repo}: files={r.file_count} rho={rho} "
                f"top-10% files take {share} of {r.test_bugfix_touches} bug-fix touches "
                f"(coverage {coverage})"
            )
        rhos = [r.spearman for r in results if r.spearman is not None]
        if len(rhos) > 1:
            console.print(f"median rho={statistics.median(rhos):.2f} across {len(rhos)} repos")
    if not results:
        raise typer.Exit(code=1)
```

Note: the command patches resolve via `black_box_unlock.validation.validate_repo` because the
module is imported as `from black_box_unlock import validation` and called as
`validation.validate_repo(...)` — do not switch to a direct `from ... import validate_repo`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_cli.py tests/unit/test_validation.py -v -p no:randomly --no-cov`
Expected: all PASS

- [ ] **Step 5: Run the full suite, lint, and format**

Run: `uv run pytest -v` then `uv run ruff check . && uv run ruff format .`
Expected: all PASS, no lint errors

- [ ] **Step 6: Commit**

```bash
git add tests/unit/test_cli.py src/black_box_unlock/cli.py
git commit -m "feat(cli): bbu validate command for hotspot self-validation"
```

---

### Task 5: Run against real repos, record numbers

**Files:**
- None (measurement step; numbers feed Task 6)

- [ ] **Step 1: Validate this repo**

Run: `uv run bbu validate --repo . --days 365`
Expected: one result line (repo is ~5 months old; adjust --days down if the train half is empty)

- [ ] **Step 2: Clone several real repos and validate**

```bash
for r in pallets/flask pallets/click encode/httpx; do
  git clone "https://github.com/$r" "/tmp/bbu-validate/$(basename $r)" 2>/dev/null
done
uv run bbu validate --repo /tmp/bbu-validate/flask --repo /tmp/bbu-validate/click --repo /tmp/bbu-validate/httpx --days 730
```

Expected: per-repo lines + median rho. Record all numbers (rho, top-decile share, coverage,
file counts) for Task 6. If a clone fails (no network), validate locally available repos
instead and note which were used.

- [ ] **Step 3: Sanity-check the numbers**

If median rho < 0.2 or top-decile share is below ~2x uniform (10%), do not bury it — investigate
(window sizes, bug-fix classifier hit rate via `--json`) and report whatever the data shows.
The published claim must match the measured numbers.

---

### Task 6: Docs — `docs/VALIDATION.md`, README, CHANGELOG

**Files:**
- Create: `docs/VALIDATION.md`
- Modify: `README.md` (new section after "Features")
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Write `docs/VALIDATION.md`**

Structure (fill measured numbers from Task 5):

```markdown
# Self-Validation: Does the Hotspot Ranking Predict Bugs?

## Method

`bbu validate` splits a repo's history at a cutoff. Files are ranked by hotspot
score (commits x indentation complexity) computed from the older half only; the
newer half supplies per-file bug-fix commit counts. If the ranking works,
yesterday's hotspots are where today's bugs get fixed.

Reported per repo:

- **Spearman rho** — rank correlation between train-half hotspot score and
  test-half bug-fix count over ranked files.
- **Top-decile share** — fraction of test-half bug-fix file-touches landing in
  the top 10% of ranked files. Uniform would be 10%.
- **Coverage** — fraction of all test-half bug-fix touches hitting ranked files
  (fixes in files the ranking never saw are visible here, not hidden).

## Results (<date>, days=<N>, split=0.5)

| Repo | Files ranked | Spearman rho | Top-10% share | Coverage |
|------|-------------|--------------|---------------|----------|
| ...  | ...         | ...          | ...           | ...      |

## Limitations

- Complexity is measured from current file contents, not contents at the
  cutoff — mild future leakage; it is the same proxy the shipped tool uses.
- Bug-fix detection is message-based (fix/bug/hotfix/defect/regression/revert,
  excluding docs/style/test/chore-style prefixes); unconventional commit
  messages under-count.
- No significance testing; sample sizes (files ranked) are listed instead.

## Reproduce

    bbu validate --repo /path/to/repo --days 730
```

- [ ] **Step 2: Add README section** (after the Features table)

```markdown
## Does the ranking actually predict bugs?

Measured with `bbu validate` (split-history: rank hotspots on the older half,
count bug-fix commits in the newer half): median Spearman rho <X> across
<repos>; the top 10% of ranked files attracted <Y>% of subsequent bug-fix
touches (uniform would be 10%). Method, per-repo numbers, and limitations:
[docs/VALIDATION.md](docs/VALIDATION.md).
```

Fill `<X>`, `<Y>`, `<repos>` from Task 5. If the numbers are weak, write what was measured.

- [ ] **Step 3: Update CHANGELOG.md**

Add under a new unreleased/dated heading following the file's existing convention:

```markdown
- `bbu validate`: split-history self-validation — Spearman correlation between
  hotspot rank and subsequent bug-fix density, plus top-decile share and
  coverage; published results in docs/VALIDATION.md
```

- [ ] **Step 4: Update CLAUDE.md CLI commands block**

Add `bbu validate --repo /path --days 730  # Hotspot-vs-bugfix self-validation` to the CLI
commands code block in CLAUDE.md.

- [ ] **Step 5: Commit**

```bash
git add docs/VALIDATION.md README.md CHANGELOG.md CLAUDE.md
git commit -m "docs: publish hotspot-vs-bugfix self-validation results"
```

---

### Task 7: Finish

- [ ] **Step 1: Run code-simplifier on changed files** (`code-simplifier:code-simplifier` agent over `validation.py`, `cli.py` changes; apply sensible suggestions)
- [ ] **Step 2: Full verification** — `uv run pytest -v` and `uv run ruff check . && uv run ruff format --check .` all green
- [ ] **Step 3: Close the issue** — `bd close BBU-6352`
- [ ] **Step 4: Commit any remaining changes, push, `bd sync`**

```bash
git push
bd sync
```
