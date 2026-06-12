# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Function-level temporal coupling in X-Ray output: same-file function pairs
  that change together (shared-commit ratio, Tornhill's formula), with a
  2-shared-commit noise floor and `--min-coupling` threshold — completes the
  faithful X-Ray feature set

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
