# Black Box Unlock - Code Map

> Bidirectional navigation between architecture diagrams and source code

## System Overview

![System overview with source navigation IDs. Entry points call analysis orchestration, which extracts churn, coupling, ownership, and defects into core models. Results reach JSON, the HTML report, and agent tools; exceptions and logging provide shared support.](../assets/diagrams/system-overview.svg)

## Data Flow

![Analysis sequence. The CLI calls run_analysis, which reads Git history, extracts forensic signals, and returns AnalysisResult. The CLI then returns JSON or asks the visualization module to generate an HTML report.](../assets/diagrams/analysis-sequence.svg)

---

### [1] Entry Points (CLI)

User-facing commands via Typer CLI.

| ID | Component | Description | File:Line |
|----|-----------|-------------|-----------|
| 1a | CLI App | Typer application with `bbu` command | [cli.py:34](../src/black_box_unlock/cli.py#L34) |
| 1a.1 | analyze_repo | Main analysis command | [cli.py:49](../src/black_box_unlock/cli.py#L49) |
| 1a.2 | version | Version info command | [cli.py:78](../src/black_box_unlock/cli.py#L78) |

---

### [2] Analysis Orchestration

Orchestrates forensic analysis by combining data from multiple sources.

| ID | Component | Description | File:Line |
|----|-----------|-------------|-----------|
| 2a | run_analysis | Main analysis pipeline | [analysis.py:30](../src/black_box_unlock/analysis.py#L30) |
| 2a.1 | collect_ci_signals | Collect failure and flaky-step data from one typed run snapshot | [github_actions.py:153](../src/black_box_unlock/cicd/github_actions.py#L153) |
| 2b | export_to_json | Serialize result to JSON | [analysis.py:155](../src/black_box_unlock/analysis.py#L155) |

#### Analysis Pipeline [2a]

![Inside run_analysis. One Git history snapshot feeds churn, ownership, coupling, and defect parsers. Their results join by path with optional CI evidence and current file complexity, then hotspot ranking and function X-Ray produce AnalysisResult with explicit CI status.](../assets/diagrams/analysis-pipeline.svg)

---

### [3] Git Forensics

Domain logic for extracting forensic signals from git history.

| ID | Component | Description | File:Line |
|----|-----------|-------------|-----------|
| 3a | parse_history_entries | Parse git log dict to FileChurn list | [churn.py:12](../src/black_box_unlock/git/churn.py#L12) |
| 3a.1 | extract_file_churn | Extract churn from git repo | [churn.py:43](../src/black_box_unlock/git/churn.py#L43) |
| 3b | analyze_temporal_coupling | Find co-changing files and count ignored bulk changesets | [coupling.py:19](../src/black_box_unlock/git/coupling.py#L19) |
| 3c | parse_ownership_from_history | Parse authors per file from git log | [ownership.py:11](../src/black_box_unlock/git/ownership.py#L11) |

#### Coupling Detection Formula [3b]

```text
coupling_ratio = co_change_count / min(commits_a, commits_b)

Commits touching more than 50 files still contribute to each file's commit
count, but are excluded from pair generation to avoid quadratic noise.

Interpretation:
  ≥0.30 (30%) → Hidden dependency (Tornhill threshold)
  ≥0.50 (50%) → Strong coupling
  ≥0.80 (80%) → Likely same logical unit
```

---

### [4] Core Data Models

Pydantic models and shared infrastructure.

| ID | Component | Description | File:Line |
|----|-----------|-------------|-----------|
| 4a | FileChurn | Churn metrics per file | [models.py:35](../src/black_box_unlock/core/models.py#L35) |
| 4a.1 | TemporalCoupling | File pair co-change | [models.py:60](../src/black_box_unlock/core/models.py#L60) |
| 4a.2 | FileOwnership | Authors per file | [models.py:79](../src/black_box_unlock/core/models.py#L79) |
| 4a.3 | FileForensics | Combined forensics | [models.py:163](../src/black_box_unlock/core/models.py#L163) |
| 4a.4 | AnalysisResult | Complete analysis output, parameters, and signal status | [models.py:286](../src/black_box_unlock/core/models.py#L286) |
| 4b | Exceptions | Custom exception classes | [exceptions.py:4](../src/black_box_unlock/core/exceptions.py#L4) |
| 4c | configure_logging | Loguru configuration | [logging.py:8](../src/black_box_unlock/core/logging.py#L8) |

#### Model Relationships [4a]

![Selected Pydantic model fields and relationships. FileChurn, FileOwnership, and TemporalCoupling aggregate into FileForensics. AnalysisResult contains those files, coupling pairs, summary, parameters, failed CI runs, flaky steps, and CI status.](../assets/diagrams/model-relationships.svg)

---

### [5] Visualization

HTML report generation with interactive visualizations.

| ID | Component | Description | File:Line |
|----|-----------|-------------|-----------|
| 5a | generate_html_report | Generate complete HTML | [html.py:807](../src/black_box_unlock/visualization/html.py#L807) |
| 5a.1 | _get_severity_class | Severity CSS class mapping | [html.py:782](../src/black_box_unlock/visualization/html.py#L782) |
| 5a.2 | HTML_TEMPLATE | Full HTML page template | [html.py:9](../src/black_box_unlock/visualization/html.py#L9) |
| 5b | build_treemap_data | Plotly treemap format | [treemap.py:6](../src/black_box_unlock/visualization/treemap.py#L6) |
| 5c | build_coupling_graph_data | Cytoscape.js graph format | [coupling_graph.py:40](../src/black_box_unlock/visualization/coupling_graph.py#L40) |
| 5c.1 | _get_directory | Extract top-level dir | [coupling_graph.py:6](../src/black_box_unlock/visualization/coupling_graph.py#L6) |
| 5c.2 | _make_node | Create graph node | [coupling_graph.py:20](../src/black_box_unlock/visualization/coupling_graph.py#L20) |

#### HTML Report Structure [5a]

![The HTML report has repository summary cards and three interactive tabs: a sortable metrics table, a Plotly hotspot treemap, and a Cytoscape coupling graph. Existing HTML views are feature-frozen.](../assets/diagrams/html-report.svg)

---

## Quick Navigation

| Area | Entry Point |
|------|-------------|
| CLI entry | [cli.py](../src/black_box_unlock/cli.py) |
| MCP server (bbu-mcp) | [mcp_server.py](../src/black_box_unlock/mcp_server.py) |
| Coupling guard | [guard.py](../src/black_box_unlock/guard.py) |
| Analysis pipeline | [analysis.py](../src/black_box_unlock/analysis.py) |
| Data models | [core/models.py](../src/black_box_unlock/core/models.py) |
| Git forensics | [git/](../src/black_box_unlock/git/) |
| Visualization | [visualization/](../src/black_box_unlock/visualization/) |
| Tests | [tests/](../tests/) |

---

## Module Structure

```text
src/black_box_unlock/
├── __init__.py              # Version
├── cli.py                   # [1a] Typer CLI
├── complexity.py            # Indentation-depth complexity proxy
├── analysis.py              # [2a] Orchestration
├── mcp_server.py            # bbu-mcp cached signals plus fresh review tool
├── review.py                # Request resolution, changed-path identity, and action selection
├── config.py                # .bbu.toml parsing
├── path_roles.py            # Project and built-in path-role classification
├── guard.py                 # Typed coupling-only cache + warnings (edit hook)
├── core/
│   ├── models.py            # [4a] Pydantic models
│   ├── exceptions.py        # [4b] Custom exceptions
│   └── logging.py           # [4c] Loguru config
├── git/
│   ├── log.py               # Native git log --numstat extraction
│   ├── churn.py             # [3a] FileChurn extraction
│   ├── coupling.py          # [3b] Coupling detection + bulk-commit cap
│   ├── ownership.py         # [3c] Ownership parsing
│   └── defects.py           # Bug-fix commit detection
├── cicd/
│   ├── models.py            # Typed WorkflowRun/Job/Step, CIAnalysis, FlakyStep
│   └── github_actions.py    # One run snapshot, partial-result-aware collection
└── visualization/
    ├── html.py              # [5a] HTML report
    ├── treemap.py           # [5b] Plotly treemap
    └── coupling_graph.py    # [5c] Cytoscape graph
```

---

## External Dependencies

| Tool | Purpose | Notes |
|------|---------|-------|
| git | Git history extraction | Native `git log --numstat`; no external tools needed |
| gh CLI | GitHub Actions data | Optional; unavailable/partial status is explicit and successful data is preserved |
| Plotly 2.27.0 | Treemap visualization | CDN-loaded JavaScript |
| Cytoscape 3.28.1 | Graph visualization | CDN-loaded JavaScript |
