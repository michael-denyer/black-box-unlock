# Self-Validation: Does the Hotspot Ranking Predict Bugs?

## Method (v2)

`bbu validate --repo PATH --days N --split F` asks one question: do the
files the hotspot ranking flags today attract tomorrow's bug fixes? It
answers with a split-history experiment that only uses information available
at the cutoff.

1. **One clock.** Commit timestamps are committer dates (`%cI`), the clock
   `git log --since` already filters on and the one that orders history. A
   rebased commit therefore lands on the side of the cutoff where it entered
   the branch, not where it was first authored. The report records
   `clock: committer`.
2. **Cutoff commit.** The cutoff is `N * (1 - F)` days ago. The cutoff
   commit is the latest first-parent commit committed before it, so the tree
   is the main line as it stood at that moment. Its SHA is in the report.
3. **Cutoff universe.** The universe is every file churned in the train half
   (commits before the cutoff) that exists in the cutoff commit's tree. Files
   deleted later stay in; files created later never appear. Complexity and
   line count are read from the cutoff tree with `git cat-file`, not from the
   working copy.
4. **Rankings.** Four rankings of the same universe, scored with the same
   metric:
   - **hotspot**: train-half commits x indentation complexity at the cutoff
     (the shipped formula).
   - **churn**: train-half commits alone.
   - **length**: lines in the file at the cutoff.
   - **random**: 200 uniformly random orderings from a fixed seed, reported
     as mean and standard deviation.
5. **Metric.** Per ranking, Spearman rho between score and post-cutoff bug-fix
   touches, and the top-decile share: the fraction of post-cutoff bug-fix
   touches on universe files that land in the top 10% of the ranking.
   Uniform would be 10%.
6. **Significance.** A one-sided permutation p for the hotspot top-decile
   share: the fraction of random draws scoring at least as high, with the
   `(b + 1) / (K + 1)` correction so 200 draws can never report 0.
7. **Sample floor.** A run with fewer than `MIN_UNIVERSE_FILES` (20) universe
   files or fewer than `MIN_TEST_BUGFIX_COMMITS` (30) post-cutoff bug-fix
   commits is flagged `insufficient_data`. The CLI prints the counts and no
   percentages; `--json` still carries every figure with the flag set.

Coverage (the fraction of all post-cutoff bug-fix touches that hit universe
files) is reported so fixes in files the ranking never saw stay visible.

## Results

Each table row is one real run of the code on this branch. Repos from the
v1 table (click, flask, pydantic, rich, fastapi, httpx) have not been re-run
under v2 and their old numbers are withdrawn; they were measured with the
HEAD tree, the author clock, and no baseline.

### black-box-unlock (2026-10-10, `--days 365 --split 0.5`)

Cutoff commit `ca867e9` (2026-04-11). Universe 55 files. 36 bug-fix commits
after the cutoff, 52 touches on the universe (coverage 43%).

| Ranking | Spearman rho | Top-10% share |
|---------|-------------:|--------------:|
| hotspot | 0.51 | 35% |
| churn | 0.45 | 27% |
| length | **0.55** | 31% |
| random (mean of 200, seed 20260612) | -0.01 | 10% (sd 7%) |

Hotspot share vs random: one-sided permutation p = 0.005.

Reading: the hotspot ranking beats random on both metrics and beats churn
alone. File length beats it on rank correlation and trails it on top-decile
share, so on this repo "long files" is a competitive predictor. One young
repo with 36 post-cutoff fixes is a thin sample; the floor is met, barely.

`--days 730` on this repo reports insufficient history: the cutoff falls a
year before the first commit (2026-01-25).

## Limitations

- Bug-fix detection is message-based (fix(ing)/bug/hotfix/defect/regression/revert
  plus repair verbs like correct/broke/crash/repair/fault/malfunction/stuck/hang,
  excluding docs/style/test/chore/ci/build/refactor/feat-style prefixes); repos
  with unconventional commit messages under-count.
- The universe only holds files churned in the train half. A file that first
  changes after the cutoff cannot be ranked, and its fixes show up as lost
  coverage.
- The random baseline is the only one the p-value is tested against. A
  hotspot score that beats random but not churn or length is reported as
  such, not hidden.
- One cutoff per run. A second split date is a second run.

## Reproduce

```bash
git clone https://github.com/pallets/click /tmp/click
bbu validate --repo /tmp/click --days 730
bbu validate --repo /tmp/click --days 730 --json
```
