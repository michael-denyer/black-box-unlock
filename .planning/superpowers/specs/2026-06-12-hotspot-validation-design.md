# Hotspot-vs-Bugfix Self-Validation (BBU-6352)

## Goal

Measure whether bbu's hotspot ranking actually predicts where bugs get fixed, across
several real repos, and publish the number in the README — the tool proving its own pitch.

## Problem with the naive version

Correlating `hotspot_score` against `bugfix_commits` from a single `run_analysis` window is
partly circular: bug-fix commits are a subset of the commits that feed the hotspot score, so
files with many commits mechanically accumulate bug-fix commits in the same window. The
published number would be inflated and easy to dismiss.

## Approaches considered

1. **Same-window correlation.** One `run_analysis` call, correlate the two columns.
   Simplest, but circular (above). Rejected.
2. **Split-history validation (chosen).** One `fetch_git_history` call over `--days` total;
   split entries at a cutoff (`--split` fraction, default 0.5). Rank files by hotspot score
   computed from the *older* half; count bug-fix commits per file in the *newer* half.
   Report Spearman rank correlation plus a concentration stat. Predictive, cheap, honest
   modulo the complexity caveat below.
3. **Full backtest with historical checkouts.** Compute indentation complexity from file
   contents *as of the cutoff commit* (git worktree/archive). Removes the leakage caveat but
   is heavy machinery for a P3 "small" item. Rejected for now; noted as future work.

## Design (approach 2)

### New module `src/black_box_unlock/validation.py`

- `spearman_rho(xs, ys) -> float | None` — average-rank Spearman implemented by hand
  (no scipy dependency). Returns `None` for n < 2 or zero variance in either ranking.
- `split_history(history, cutoff) -> (train, test)` — partition entries by ISO timestamp;
  entries strictly before the cutoff go to train, the rest to test.
- `validate_repo(repo_path, days=730, split=0.5) -> ValidationResult` — orchestration:
  fetch history once, split at `now - days*(1-split)`, compute per-file hotspot scores from
  the train half (train commits × current indentation complexity — same formula the tool
  ships), count test-half bug-fix commits via the existing `bugfix_counts`, correlate.
- `ValidationResult` (pydantic, local to this module — it is an experiment artifact, not part
  of the analysis output contract): repo name, days, split, file count, spearman rho,
  top-decile bug-fix share, bug-fix coverage, test-window bug-fix totals.

### Metric definitions

- **Universe**: files that appear in the train window AND still exist on disk (the shipped
  ranking only covers existing files). Files with no test-window fixes count as 0.
- **Spearman rho**: hotspot score vs test-window bug-fix count over the universe.
- **Top-decile share**: sort universe by train hotspot score descending; share of
  test-window bug-fix file-touches landing in the top 10% (ceil) of files. Mirrors the
  "2-8% of files cause 60-90% of defects" pitch directly. `None` if the test window has
  no bug-fix touches in the universe.
- **Coverage**: fraction of *all* test-window bug-fix file-touches that hit the universe.
  Reported so the headline can't silently exclude bug-fixes in files the ranking never saw.

### CLI

`bbu validate [--repo PATH]... [--days 730] [--split 0.5] [--json]`

- `--repo` repeatable; default `[.]`. Prints one result line/table row per repo and, for
  multiple repos, the median rho. `--json` emits the raw `ValidationResult` list.
- Empty train or test window → clear error per repo (suggest larger `--days`), exit 1 only
  if every repo failed.

### Docs

- README: short "Does the ranking actually predict bugs?" section with the measured numbers
  (median rho + per-repo range, top-decile share) and a one-line method summary linking to
  `docs/VALIDATION.md`.
- `docs/VALIDATION.md`: method, metric definitions, limitations.
- CHANGELOG entry; close BBU-6352.

### Validation run

Run `bbu validate` against this repo plus several real public repos (e.g. flask, click,
httpx — full clones into /tmp), publish the resulting numbers in the README. Repos chosen
for active history and conventional-commit-ish messages so the bug-fix classifier has signal.

## Known limitations (documented, accepted)

- Complexity is measured from current file contents, not contents at the cutoff — mild
  future leakage, but it is the exact proxy the shipped tool uses (approach 3 fixes this).
- Bug-fix detection is message-based; repos with unconventional commit messages
  under-count.
- No significance testing; with hundreds of files, |rho| ≳ 0.2 is comfortably non-noise,
  and the README states sample sizes.

## Testing

TDD throughout: unit tests for `spearman_rho` (monotonic, inverse, ties, constant input),
`split_history` (cutoff boundary), universe/metric edge cases (no bugfixes, deleted files),
plus a CLI test with `validate_repo` patched, following existing test patterns.
