# Analyze Repo CLI Design

**Task:** BBU-pj6f - CLI: bbu analyze-repo
**Date:** 2026-01-25

## Summary

CLI command that runs git forensics and outputs JSON (for agent use) or static HTML report (for visual browsing). Follows Tornhill's methodology with separate metrics, no combined score.

## Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Primary output | JSON to stdout | Agent/programmatic consumption |
| Visual output | Static HTML file | Self-contained, opens in browser, no server |
| Combined score | None | No established methodology; would be arbitrary |
| Metrics display | Separate columns | Hotspot, Authors, Coupling shown independently |
| Hotspot formula | commits × lines_changed | Tornhill's approach (churn × complexity proxy) |
| Complexity proxy | lines_changed | True AST complexity deferred (see BBU-8lt) |

## CLI Interface

```bash
bbu analyze-repo [OPTIONS]

Options:
  --days INTEGER        Days of history to analyze (default: 30)
  --limit INTEGER       Max files to show (default: 20)
  --min-coupling FLOAT  Coupling threshold (default: 0.3)
  --html                Generate HTML report and open in browser
  --output PATH         Output file path (default: stdout for JSON, ./report.html for HTML)
```

## Output Formats

### JSON (default)

```json
{
  "repo": "black-box-unlock",
  "analyzed_days": 30,
  "generated_at": "2026-01-25T15:30:00Z",
  "files": [
    {
      "path": "src/auth/handler.py",
      "commits": 42,
      "lines_changed": 1234,
      "hotspot_score": 51828,
      "authors": ["alice@example.com", "bob@example.com"],
      "author_count": 2,
      "is_high_risk": false,
      "coupled_with": [
        {"file": "src/auth/tokens.py", "ratio": 0.85}
      ]
    }
  ],
  "summary": {
    "total_files": 142,
    "high_risk_ownership": 8,
    "coupled_pairs": 12
  }
}
```

### HTML Report

Self-contained HTML with embedded CSS/JS:
- Summary stats header
- Sortable/filterable table
- Color coding: yellow for high-risk ownership, coupling shown inline
- No external dependencies

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      CLI (cli.py)                           │
│  bbu analyze-repo --days 30 --html                          │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                   analyze.py (new)                          │
│  run_analysis(repo_path, days) -> AnalysisResult            │
│  - Calls gmap, parses JSON                                  │
│  - Computes churn, ownership, coupling                      │
│  - Joins by file path                                       │
│  - Computes hotspot scores                                  │
└─────────────────────────────────────────────────────────────┘
                              │
            ┌─────────────────┼─────────────────┐
            ▼                 ▼                 ▼
┌───────────────────┐ ┌───────────────┐ ┌───────────────────┐
│    churn.py       │ │ ownership.py  │ │   coupling.py     │
│ extract_file_churn│ │ parse_owner.. │ │ detect_temporal.. │
└───────────────────┘ └───────────────┘ └───────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│               visualization/ (new directory)                │
│  - json_output.py: serialize to JSON                        │
│  - html_report.py: generate HTML report                     │
└─────────────────────────────────────────────────────────────┘
```

## Data Model

```python
class FileForensics(BaseModel):
    """Combined forensics for a single file."""
    path: str
    commits: int
    lines_changed: int
    hotspot_score: int  # commits × lines_changed
    authors: list[str]
    author_count: int
    is_high_risk: bool  # author_count > 3
    coupled_with: list[CouplingInfo]

class CouplingInfo(BaseModel):
    """Coupling relationship for display."""
    file: str
    ratio: float

class AnalysisResult(BaseModel):
    """Complete analysis output."""
    repo: str
    analyzed_days: int
    generated_at: datetime
    files: list[FileForensics]
    summary: AnalysisSummary

class AnalysisSummary(BaseModel):
    """Summary statistics."""
    total_files: int
    high_risk_ownership: int
    coupled_pairs: int
```

## Test Strategy

| Test | Purpose |
|------|---------|
| FileForensics model | Creation, hotspot_score property |
| run_analysis with mock gmap | Returns correct AnalysisResult |
| JSON output | Serializes correctly |
| HTML output | Generates valid HTML with data |
| CLI integration | End-to-end with real repo |
| Error handling | Missing gmap, not a git repo |

## Future Work

- BBU-8lt: AST-based complexity analysis
- BBU-1ee: Full forensic output from gmap
- BBU-vk7d: Rich visualizations epic (VSCode webview, etc.)
