

<table width="100%">
<tr>
<td width="200">
<img src="assets/logo.png" alt="Black Box Unlock" width="200">
</td>
<td valign="middle">

[![CI](https://github.com/michael-denyer/black-box-unlock/actions/workflows/ci.yml/badge.svg)](https://github.com/michael-denyer/black-box-unlock/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)

# Black Box Unlock

*Mischief. Mayhem. Merge conflicts. Exposed.*

</td>
</tr>
</table>

Code forensics tool based on Adam Tornhill's ["Your Code as a Crime Scene"](https://pragprog.com/titles/atcrime2/your-code-as-a-crime-scene-second-edition/). Key insight: **2-8% of files cause 60-90% of defects**.

## Installation

```bash
uv pip install -e .
```

## Usage

```bash
# Analyze last 30 days of git history, output JSON
bbu analyze-repo --days=30

# Generate interactive HTML report
bbu analyze-repo --days=30 --output=html > report.html

# Adjust coupling detection threshold (default 0.3)
bbu analyze-repo --min-coupling=0.5 --output=html > report.html
```

## Features

| Signal | Description |
|--------|-------------|
| **Hotspot Score** | churn × complexity - identifies unstable code |
| **Temporal Coupling** | Files changing together >30% reveal hidden dependencies |
| **Ownership Risk** | >3 authors + high churn = coordination problems |

### HTML Report

The HTML report includes three interactive views:

- **Table** - Sortable file metrics with severity coloring
- **Hotspots** - Plotly treemap showing file churn by directory
- **Coupling** - Cytoscape.js network graph of temporal coupling

```mermaid
flowchart LR
    Git[Git History] --> Analyze[bbu analyze-repo]
    Analyze --> JSON[JSON Output]
    Analyze --> HTML[HTML Report]
    HTML --> Treemap[Hotspot Treemap]
    HTML --> Graph[Coupling Graph]
```

## Architecture

See [ARCHITECTURE.md](ARCHITECTURE.md) for full details.

```
src/black_box_unlock/
├── cli.py              # Typer CLI
├── core/               # Pydantic models, exceptions
├── git/                # Churn, coupling, ownership extraction
├── analysis.py         # Orchestration
└── visualization/      # HTML, treemap, coupling graph
```

## Development

```bash
# Run tests
uv run pytest -v

# Lint and format
uv run ruff check . && uv run ruff format .

# Verbose output for debugging
bbu --verbose analyze-repo
```

## License

MIT
