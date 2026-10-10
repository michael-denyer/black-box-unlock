# Self-Validation: Does the Hotspot Ranking Predict Bugs?

## Method (v2)

`bbu validate --repo PATH --days N --split F` asks one question: do the
files the hotspot ranking flags today attract tomorrow's bug fixes? It
answers with a split-history experiment that only uses information available
at the cutoff.

1. **One clock.** Commit timestamps are committer dates (`%cI`), the clock
   `git log --since` already filters on and the one that orders history. The
   report records `clock: committer`.
2. **Cutoff commit.** The cutoff is `N * (1 - F)` days ago. The cutoff
   commit is the latest first-parent commit committed before it, so the tree
   is the main line as it stood at that moment. Its SHA is in the report.
3. **Ancestry split.** The train half is every commit in the window
   reachable from the cutoff commit (`git log <cutoff>`); the test half is
   every commit reachable from `HEAD` but not from the cutoff
   (`<cutoff>..HEAD`). A side-branch commit made before the cutoff date but
   merged after it is therefore test, which matches the cutoff tree that
   never saw it.
4. **Cutoff universe.** The universe is every file churned in the train half
   that exists as a blob in the cutoff commit's tree. Files deleted later
   stay in; files created later never appear; a path that names a directory
   at the cutoff is skipped. Complexity and line count are read from the
   cutoff tree with `git cat-file`, not from the working copy.
5. **Rankings.** Four rankings of the same universe, scored with the same
   metric:
   - **hotspot**: train-half commits x indentation complexity at the cutoff
     (the shipped formula).
   - **churn**: train-half commits alone.
   - **length**: `splitlines()` of the blob at the cutoff. Every blob counts,
     so data files such as `uv.lock` rank by their line count too.
   - **random**: 200 uniformly random orderings from a fixed seed, reported
     as mean and standard deviation.
6. **Metric.** Per ranking, Spearman rho between score and post-cutoff bug-fix
   touches (average ranks for ties), and the top-decile share: the fraction
   of post-cutoff bug-fix touches on universe files that land in the top 10%
   of the ranking. Files tied at the boundary score share the slots they
   compete for pro rata, so the share does not depend on path order. Uniform
   would be 10%.
7. **Significance.** A one-sided permutation p for the hotspot top-decile
   share: the fraction of random draws scoring at least as high, with the
   `(b + 1) / (K + 1)` correction so 200 draws can never report 0. When no
   draw reaches the observed share the value is a ceiling, and the report
   prints it as `p<0.005 (no draw reached it)`.
8. **Sample floor.** A run with fewer than `MIN_UNIVERSE_FILES` (20) universe
   files or fewer than `MIN_TEST_BUGFIX_COMMITS` (30) post-cutoff bug-fix
   commits that change files is flagged `insufficient_data`. Merge commits
   change no files, so a merge whose subject names a `fix/` branch does not
   count. The CLI prints the counts and no percentages, coverage included;
   `--json` still carries every figure with the flag set. Such repos are
   left out of the median, and a run with no usable repo exits 1.

Coverage (the fraction of all post-cutoff bug-fix touches that hit universe
files) is reported so fixes in files the ranking never saw stay visible.

## Results

Each table row is one real run of the code on this branch. Repos from the
v1 table (click, flask, pydantic, rich, fastapi, httpx) have not been re-run
under v2 and their old numbers are withdrawn; they were measured with the
HEAD tree, the author clock, and no baseline.

### black-box-unlock (2026-10-10, `--days 365 --split 0.5`, HEAD `c7278a3`)

Cutoff date 2026-04-11; cutoff commit `ca867e9`, committed 2026-01-26. The
train half is 79 commits over two days, 2026-01-25 to 2026-01-26: the repo
has no commits between 2026-01-27 and 2026-06-11, so the cutoff date sits in
that gap. The test half is 2026-06-12 to HEAD. Universe 55 files. 37 bug-fix
commits after the cutoff, 67 touches on the universe (coverage 41%).

| Ranking | Spearman rho | Top-10% share |
|---------|-------------:|--------------:|
| hotspot | 0.50 | 30% |
| churn | 0.51 | 30% |
| length | **0.56** | 24% |
| random (mean of 200, seed 20260612) | -0.01 | 10% (sd 7%) |

Hotspot share vs random: one-sided permutation p = 0.010 (one of 200 draws
reached 30%).

Reading: the hotspot ranking beats random on both metrics. It does not beat
churn alone: the two rankings tie on top-decile share and churn is a hair
ahead on rank correlation, so on this repo the complexity factor adds
nothing to churn. File length beats both on rank correlation and trails on
top-decile share. One young repo with 37 post-cutoff fixes is a thin sample,
and the count includes the fix commits on the branch that produced this
table; on `origin/main` at `4d2075d` it is 31, still above the floor.

Other windows on this repo: `--days 300` lands the cutoff in the same gap
and gives the same table. `--days 250` fails with "need commits on both
sides": the window starts 2026-02-02, after the last train commit, so the
train half is empty. `--days 200` puts the cutoff at 2026-07-02 and reports
`insufficient data: 20 post-cutoff bug-fix commits < 30`. `--days 730` fails
the same way as 250: the cutoff (2025-10-10) falls three and a half months
before the first commit (2026-01-25).

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
- Commits over the coupling policy's `max_changeset_size` (50 by default, or
  the `[coupling]` table in `.bbu.toml`) are excluded from both halves, as
  `analyze-repo` excludes them, so a 60-file `fix:` commit is not a fix on 60
  files.

## Reproduce

```bash
git clone https://github.com/pallets/click /tmp/click
bbu validate --repo /tmp/click --days 730
bbu validate --repo /tmp/click --days 730 --json
```
