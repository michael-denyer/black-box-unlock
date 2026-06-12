# Architecture

Code forensics tool based on Adam Tornhill's "Your Code as a Crime Scene".
Signals are extracted from git history and GitHub Actions, joined per file,
and served as JSON, an HTML report (frozen), and MCP tools.

## Module layout

```
src/black_box_unlock/
├── cli.py                  # Typer CLI: bbu analyze-repo / version
├── complexity.py           # Indentation-depth complexity proxy
├── analysis.py             # Pipeline: fetch -> parse -> join -> AnalysisResult
├── mcp_server.py           # FastMCP server: bbu-mcp (Milestone B)
├── core/
│   ├── models.py           # Pydantic models (FileForensics, AnalysisResult, ...)
│   ├── exceptions.py       # NotAGitRepoError, GitToolNotFoundError
│   └── logging.py          # loguru configuration (--verbose)
├── git/
│   ├── log.py              # Native git log --numstat extraction
│   ├── churn.py            # FileChurn aggregation
│   ├── coupling.py         # Temporal coupling (Tornhill ratio)
│   ├── ownership.py        # Authors per file
│   └── defects.py          # Bug-fix commit detection
├── cicd/
│   ├── models.py           # WorkflowRun, BuildFailure, FlakyStep
│   └── github_actions.py   # gh CLI fetchers, flaky detection
└── visualization/          # FROZEN - no new features
    ├── html.py             # Tabbed HTML report
    ├── treemap.py          # Plotly hotspot treemap
    └── coupling_graph.py   # Cytoscape coupling graph
```

## Signals

| Signal | Source | Formula |
|--------|--------|---------|
| Hotspot score | git + file contents | commits x indentation complexity |
| Temporal coupling | git | co_changes / min(commits_a, commits_b), threshold 0.3 |
| Ownership risk | git | > 3 authors |
| Bug-fix commits | git messages | fix/bug/hotfix/revert/regression markers per file |
| Build failures | gh CLI | files changed in failing workflow runs |
| Flaky steps | gh api | step failed attempt N, passed attempt M>N (re-runs only) |

## Data flow

```mermaid
flowchart LR
    Git[git log --numstat] --> Parse[churn / coupling /<br/>ownership / defects]
    GH[gh CLI + REST] --> CI[build failures /<br/>flaky steps]
    Parse --> Join[run_analysis join]
    CI --> Join
    Join --> JSON[JSON]
    Join --> HTML[HTML report - frozen]
    Join --> MCP[bbu-mcp tools]
```

## Degraded modes

- Not a git repo -> `NotAGitRepoError`, CLI prints error, exit 1
- git missing -> `GitToolNotFoundError`, same handling
- gh missing/unauthenticated -> loguru warning, CI signals empty, analysis continues

## Roadmap

Tracked in beads (`bd ready`) and `.planning/superpowers/plans/2026-06-12-agent-native-pivot.md`.
Decided direction: agent-native (MCP + plugin) on top of corrected signals; HTML frozen;
no IDE telemetry; no PR-flow dashboard signals.
