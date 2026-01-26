# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
