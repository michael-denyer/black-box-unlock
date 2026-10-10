# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed

- `bbu validate` v2. The universe and its complexity are read from the tree
  at the cutoff commit instead of HEAD, history is split by ancestry of the
  cutoff commit on the committer clock that `git log --since` already
  filters on, and the hotspot score is reported beside churn-only,
  file-length, and seeded random (200 draws) baselines with a one-sided
  permutation p-value. Runs with fewer than 20 universe files or 30
  post-cutoff bug-fix commits that change files are flagged
  `insufficient_data`, print counts instead of percentages, are left out of
  the median, and exit 1 when no repo is usable. `ValidationReport` replaces
  `ValidationResult`; `fetch_git_history` gains a `clock` keyword.
  `docs/VALIDATION.md` is re-derived from the v2 method and the v1 per-repo
  table is withdrawn.

## [1.5.2] - 2026-10-10

### Fixed

- CI failures on merge commits now implicate the files the merge brought in
  (the diff against its first parent). Before, a merge or merge-queue commit
  listed no files and its failure was attributed to nothing
- A flaky step's `flaky_rate` is now `flaky_runs / runs`, over the runs in which
  the step executed. Before, it divided recoveries by attempt observations of
  flaky runs only, so retries inflated it and stable runs never counted. The
  step output gains `runs` and `flaky_runs`. The rate covers only the re-run
  runs examined, since jobs are fetched only for those
- `gh api` calls time out after 60 seconds and report the timeout in
  `ci_status.errors`. Workflow runs are fetched across up to 10 pages of 100
  instead of the first page, and only runs created within the analysis `--days`
  window count. `get_ci_failures` and `get_flaky_steps` cover the last 30 days
- Flaky detection stays within one workflow run, so a failure on one commit
  followed by a pass on another is not flaky
- The coupling guard cache moved from `.bbu/cache.json` in the working tree to
  `bbu/cache.json` in the worktree's git dir, and the guard refuses to write
  through a symlink. A committed `.bbu` symlink could make the edit hook
  overwrite an arbitrary file. You can delete old `.bbu/` directories
- `bbu review-change --base` reads history only up to the merge base, so the
  branch under review no longer counts its own commits as prior evidence
- Ownership applies `.mailmap` (`%aE`) and ignores bot authors such as
  `dependabot[bot]` and `noreply@github.com`. The review focus action uses
  `HIGH_RISK_AUTHOR_THRESHOLD` instead of a literal 3
- The edit hook no longer discards stderr. `coupling-guard-hook` finds the
  repository root with git, so it works from subdirectories, and still warns
  when the cache write fails. Edits outside the repository are ignored. A
  failure inside a repository appends a line to `<git-dir>/bbu/hook.log`,
  capped at 200 lines, which `bbu doctor` reports
- CI attribution runs `git show` through `run_git`, so non-ASCII paths come
  back unquoted and match history paths, and a failure's git stderr now
  appears in the CI warning and status errors
- `--min-coupling` on `analyze-repo`, `review-change`, and `xray` must be
  between 0 and 1, and `review-change --min-shared-revisions` must be at least
  1. Out-of-range values exit 2 with a usage error instead of a traceback
- The README states that the 46% top-decile median covers the four repos with
  enough bug-fix signal. The six-repo median is 39.5%
- X-Ray attributes deleted lines through each commit's parent snapshot. Added
  lines still use the commit's own snapshot. Before, deletions went to the
  function after the gap or were lost, so a commit that removed one function
  could credit its neighbour
- X-Ray no longer guesses for files without a git diff driver (such as `.js`).
  `bbu xray` returns `skipped: "unsupported language"`, and the top-hotspot
  pass sets `xray_skipped` on the file
- X-Ray survives snapshots that exceed the `ast` recursion limit. Function
  `complexity` and `hotspot_score` are `null` with a
  `score_unavailable_reason` when the current snapshot cannot be parsed
- `docs/XRAY.md` replaces the "negligible cost" claim for `--xray-top 5` with
  measured timings

## [1.5.1] - 2026-10-10

### Changed

- The package keywords now match the GitHub repository topics. They add
  `code-review`, `code-insights`, `clean-code`, `agent-plugin`, `claude-code`,
  and `claude-plugin`
- `run_change_review` takes one `ChangeReviewRequest` (selector, optional
  profile, and policy overrides) and resolves `.bbu.toml` itself.
  `resolve_review_settings`, `ReviewOverrides`, and `ResolvedReviewSettings`
  are removed from `black_box_unlock.config`. The `bbu review-change` command
  and the MCP `review_change` tool keep their arguments and results

### Fixed

- The `maid` prek hook now checks every Markdown file. maid validates only its
  first file argument, so a file was checked only when it came first in a
  batch, and `docs/CODEMAP.md` carried errors that CI never reported
- `docs/CODEMAP.md` now passes maid 0.0.29, which rejects three valid Mermaid
  constructs. The `git log --numstat` participant spells its dashes as `#45;`
  and renders the same text. In the model class diagram, relationships are
  dashed (`..>`) instead of solid (`-->`) and list types render as `list<str>`
  instead of `list[str]`
- Change review keeps a file's history when the selected change renames it.
  The renamed path previously reported zero commits, bug-fix commits, and
  authors, so `focus_review` could not fire for it. Earlier churn, defects,
  ownership, coupling, and CI evidence now follow the current path, and the
  rename revision counts once

## [1.5.0] - 2026-10-10

### Added

- A `LICENSE` file with the MIT text that `pyproject.toml` and the README
  already declare, so GitHub and built distributions carry the licence

### Changed

- Updated locked dependencies: mcp 1.29.0 to 2.2.0, typer 0.27.0 to 0.27.2,
  pydantic 2.13.4 to 2.13.5, pytest-randomly 4.1.0 to 5.0.0, ruff 0.16.0 to
  0.16.9, prek 0.4.11 to 0.5.4, pyrefly 1.1.1 to 1.3.1, zizmor 1.28.0 to
  1.30.1, and the hatchling build pin 1.31.0 to 1.32.4
- The MCP server now uses the mcp 2 `MCPServer` class, and the `mcp`
  requirement is now `>=2.2.0,<3`. Tool names, arguments, and results are
  unchanged; tool errors are raised as `ToolError` so clients still see the
  message

### Fixed

- The `lychee` prek hook no longer fails with exit 100 on every commit made
  from a linked git worktree. It is pinned to the upstream fix for
  lycheeverse/lychee#2292 and still installs lychee 0.24.2

### Security

- Updated locked PyJWT (2.13.0 to 2.15.1), anyio (4.13.0 to 4.15.1), and
  cryptography (48.0.1 to 50.0.2) to releases that clear their open
  advisories; typing-extensions moved to 4.16.0 as an anyio requirement

## [1.4.0] - 2026-07-30

### Added

- `.bbu.toml` project configuration with ordered path-role rules, named review
  profiles, a selectable default profile, and CLI/MCP overrides
- Opt-in `inspect_ci_failures` review actions with the failed workflow name,
  run ID and URL, commit, timestamp, and implicated changed paths
- `bbu doctor` validation for project configuration
- Pyrefly, Markdown link checks, GitHub Actions lint and security checks,
  locked-dependency auditing, and CodeQL

### Changed

- Local Git hooks now run through `prek`; repository hygiene, Ruff, Pyrefly,
  GitHub Actions lint and security checks, Markdown links, Mermaid rendering,
  and locked-dependency auditing run through the same gate in CI
- Dependabot now updates both GitHub Actions and the `uv` lockfile, with grouped
  weekly updates and a seven-day cooldown
- CodeQL scans Python source on pull requests, pushes to `main`, and weekly
- CI failure output now preserves failed-run details and states that changed
  paths are implicated rather than proven causal

### Fixed

- Updated locked Click and MCP releases after dependency auditing found three
  published vulnerabilities
- Removed the last stale documentation reference to the retired local issue
  tracker

## [1.3.0] - 2026-07-30

### Added

- `bbu review-change` and the uncached MCP `review_change` tool review branch,
  staged, or working-tree changes and return at most three typed,
  evidence-backed actions
- `/review-change` plugin command and `bbu doctor` activation diagnostics
- Fixed, explainable path roles for source, tests, docs, config, migrations,
  generated files, and other paths
- Change provenance with resolved revisions, selected Git layers, observation
  time, parameters, and explicit cache status

### Changed

- Temporal coupling exposes shared and per-file revision counts plus the 95%
  Wilson lower bound; repeated evidence now ranks ahead of perfect ratios from
  tiny samples
- Review and ambient hook actions require at least two shared revisions by
  default
- The coupling cache is keyed to `HEAD` as well as its TTL
- The plugin hook parses its JSON payload in Python and no longer requires
  `jq`
- MCP is capped to the compatible major range `>=1.27,<2`

## [1.2.0] - 2026-07-07

### Added

- Function-level temporal coupling in X-Ray output: same-file function pairs
  that change together (shared-commit ratio, Tornhill's formula), with a
  2-shared-commit noise floor and `--min-coupling` threshold — completes the
  faithful X-Ray feature set
- `xray_failed` flag on file forensics so JSON/MCP consumers can tell an X-Ray
  crash from a file that genuinely has no attributable functions (both leave
  `functions` empty)

### Fixed

- X-Ray no longer silently degrades on unexpected git failures: `_show` routes
  through the single `run_git` entry point and logs corruption/permission
  errors, while a path simply absent at a revision stays silent as before
- Coupling guard recovers from a corrupt or wrong-shape cache by rebuilding,
  instead of crashing on unparseable JSON or re-warning on every edit until the
  24h TTL; the CLI guard now logs when it skips so a silently-dead guard is
  diagnosable
- `FlakyStepStats` rejects impossible counts (0 ≤ flaky_count ≤ failures ≤
  total_attempts), keeping `flaky_rate` within [0, 1]
- Bug-fix prefix exclusion list in CLAUDE.md, ARCHITECTURE.md and VALIDATION.md
  corrected to match the code (the list also excludes `ci`/`build`/`refactor`)
- HTML treemap rendered blank when a path was both a file and a directory across
  history (duplicate Plotly node id blanks the whole treemap); node ids are now
  globally deduplicated
- `analyze-repo` no longer crashes on a malformed-but-valid-JSON notebook
  (cleared cell `source`, non-dict cell, non-dict top level); the indentation
  scorer validates notebook shape at the parse boundary and degrades to 0, like
  it already handles unparseable notebook JSON
- A file scored 0 complexity because of a generator marker in its header is now
  logged at INFO, so the suppression is discoverable with `-v` instead of the
  file silently dropping off the hotspot ranking

### Changed

- Hotspot complexity now reflects code, not file size or generated content.
  Serialized-data, lockfile, and asset files
  (`.json`/`.jsonl`/`.csv`/`.tsv`/`.lock`/`.map`/`.svg`/`*.min.js|css`) score 0,
  so a giant JSON seed or lockfile can no longer top the ranking. Notebooks
  (`.ipynb`) are scored over their code cells only, ignoring the JSON envelope
  that previously inflated them. Files carrying a generator marker in their
  first 2KB (`DO NOT EDIT`, `@generated`, `code generated by`, `auto-generated`)
  score 0, catching generated code the extension filter cannot (Rails
  `schema.rb`, protoc output). Config/markup (`.yaml`/`.yml`/`.xml`) stays
  scored. (Validated across three real repos: a clean code repo's hotspot↔
  bug-fix Spearman of 0.93 held; a data-heavy repo's generated `schema.rb`, its
  former #1 hotspot, is now correctly dropped.)
- Bug-fix detection broadened with measured precision. Added the `fixing`
  inflection (the `-ing` form was a real miss) plus `correct`/`broke`/`crash`/
  `repair`/`fault`/`malfunction`/`stuck`/`hang`/`hung`. `fail`/`failure`/`error`/
  `problem` were evaluated against 2,503 real commits and rejected as
  high-false-positive (feature work like "add error handling"); a precision test
  pins the rejection. Lifted a data-heavy repo's detected fixes 128→140 with no
  precision loss on a clean repo.
- `feat:`-prefixed commits are now excluded from defect classification. The
  broadened vocabulary made feature commits mentioning a defect noun (`feat: add
  crash reporter`) count as fixes, inflating feature files' bug-fix density.
  `perf:` stays counted, since perf commits are often genuine defect repairs.

## [1.1.0] - 2026-06-12

### Added

- Function-level forensics (Tornhill X-Ray): per-function churn × complexity via
  `bbu xray FILE`, the `xray_file` MCP tool, and auto X-Ray of top hotspots in
  `analyze-repo` (`--xray-top`, default 5) — [docs/XRAY.md](docs/XRAY.md)
- `bbu validate`: split-history self-validation — Spearman correlation between
  hotspot rank and subsequent bug-fix density, plus top-decile share and
  coverage; results published in [docs/VALIDATION.md](docs/VALIDATION.md)
  (median rho 0.46 across six real repos)
- Self-hosted plugin marketplace (`/plugin marketplace add michael-denyer/black-box-unlock`)

### Fixed

- `analyze-repo` JSON output used Rich's console.print, which wraps at terminal
  width and corrupts JSON strings longer than ~80 chars (exposed by X-Ray's
  qualified function names)
- Coupling guard names files deterministically when ratios tie (path ascending)

### Changed

- CI hardening: all workflow actions SHA-pinned, Dependabot for actions, ruff
  pinned identically in pyproject and pre-commit, hatchling pinned exactly
- CI dogfood job: bbu analyzes its own repository on every push
- osv-scanner scans uv.lock on pull requests
- Tests run randomized (pytest-randomly), parallel (pytest-xdist -n 3), with
  30s timeouts (pytest-timeout)
- Pre-commit now lints markdown (markdownlint-cli2) and validates mermaid
  diagrams twice (maid syntax + mmdc renderer parity)
- YAML form issue templates; blank issues disabled
- Release workflow artifact actions bumped to current SHAs (Node 24 ready)

## [1.0.0] - 2026-06-12

### Added

- Bug-fix commit density per file
- Flaky CI step detection in analysis output
- `--repo` flag to analyze a repository other than the cwd
- `bbu-mcp` MCP server: six forensic tools as agent context
- Claude Code plugin: `/analyze`, `/hotspots`, git-forensics agent, ambient coupling guard hook
- PyPI publishing via trusted publishing with Sigstore attestations

### Fixed

- Version mismatch: `pyproject.toml` and `__init__.py` said 0.2.0 after the 0.3.0 release
- Missing git binary reports a clear error message instead of a raw traceback

### Changed

- Git history extraction is now native (`git log --numstat`) — the gmap Rust CLI is no longer required
- Hotspot score is now commits × indentation complexity (was commits × lines changed)
- Plugin restructured to spec (components at repo root, lean manifest)

## [0.3.0] - 2026-01-26

### Added

- CI/CD build failure tracking via GitHub Actions (BBU-b7oh)
  - Fetches workflow runs via `gh` CLI
  - Attributes failures to files changed in failing commits
  - Displays "Build Failures" column in HTML report
  - `--no-ci` flag to skip CI analysis when GitHub access unavailable
  - Graceful degradation when CI data unavailable
- Cytoscape.js network graph for temporal coupling visualization (BBU-ex2p)
  - Nodes colored by directory to reveal cross-module coupling
  - Red edges highlight hidden dependencies between modules
  - Interactive pan/zoom with force-directed layout
- Loguru logging with `--verbose` flag for debug output

## [0.2.0] - 2026-01-25

### Added

- Interactive Plotly treemap visualization for file hotspots (BBU-6335)
- Tabbed HTML report with Table, Hotspots, and Coupling views
- Collapsible help section explaining metrics (hotspot score, ownership risk, coupling)
- HTML report generator with severity-based coloring
- File churn extraction from git history using gmap (BBU-8b03)
- Temporal coupling detection from git commits (BBU-f3v2)
- File ownership spread calculation (BBU-k4e2)
- Core data models: `FileChurn`, `TemporalCoupling`, `FileOwnership`
- Custom exceptions: `NotAGitRepoError`, `GitToolNotFoundError`
- Integration tests for git churn extraction
