# Self-Validation: Does the Hotspot Ranking Predict Bugs?

## Method

`bbu validate` splits a repo's history at a cutoff. Files are ranked by hotspot
score (commits × indentation complexity) computed from the older half only; the
newer half supplies per-file bug-fix commit counts. If the ranking works,
yesterday's hotspots are where today's bugs get fixed.

Reported per repo:

- **Spearman rho** — rank correlation between train-half hotspot score and
  test-half bug-fix count over ranked files.
- **Top-decile share** — fraction of test-half bug-fix file-touches landing in
  the top 10% of ranked files. Uniform would be 10%.
- **Coverage** — fraction of all test-half bug-fix touches hitting ranked files
  (fixes in files the ranking never saw are visible here, not hidden).

## Results (2026-06-12, `--days 730 --split 0.5`)

| Repo | Files ranked | Spearman rho | Top-10% share | Bug-fix touches | Coverage |
|------|-------------:|-------------:|--------------:|----------------:|---------:|
| click (8a1b1a3) | 67 | **0.62** | 49% | 93 | 67% |
| flask (36e4a824) | 63 | 0.50* | 36% | 14 | 78% |
| pydantic (2700a3594) | 308 | **0.48** | 55% | 109 | 49% |
| rich (46cebbb0) | 79 | **0.45** | 21% | 42 | 79% |
| fastapi (d3e6a2931) | 1044 | **0.24** | 43% | 174 | 55% |
| httpx (b5addb6) | 55 | -0.23* | 0% | 2 | 100% |

\* Too few test-window bug-fix touches (< 30) for the correlation to mean much;
listed for completeness, excluded from the headline. The inclusion criterion is
sample size, not result — and the median is 0.46 either way (all six repos, or
just the four with enough signal).

**Headline: median Spearman rho 0.46; the top 10% of ranked files attracted a
median 46% of subsequent bug-fix touches (uniform would be 10%) in repos with
enough bug-fix signal.**

For reference, this repo itself (young, ~5 months of history, `--days 240`):
rho 0.36, top-10% share 36% over 22 touches, coverage 47%.

## Limitations

- Complexity is measured from current file contents, not contents at the
  cutoff — mild future leakage; it is the same proxy the shipped tool uses.
- Bug-fix detection is message-based (fix(ing)/bug/hotfix/defect/regression/revert
  plus repair verbs like correct/broke/crash/repair/fault/malfunction/stuck/hang,
  excluding docs/style/test/chore/ci/build/refactor-style prefixes); repos with unconventional
  commit messages under-count.
- No significance testing; file counts and touch counts are listed so readers
  can judge sample sizes themselves.
- Coverage below 100% means some bug-fixes landed in files the train window
  never saw (new files, or files churned only after the cutoff) — the ranking
  cannot predict those by construction.

## Reproduce

```bash
git clone https://github.com/pallets/click /tmp/click
bbu validate --repo /tmp/click --days 730
```
