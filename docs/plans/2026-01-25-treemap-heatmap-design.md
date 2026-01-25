# Treemap Hotspot Heatmap Design

**Issue:** BBU-6335
**Date:** 2026-01-25

## Overview

Upgrade the HTML report to a tabbed dashboard with an interactive treemap visualization of file hotspots. Rectangle size shows file size (lines_changed), color intensity shows hotspot score.

## Architecture

```
┌─────────────────────────────────────────────────────┐
│  Code Forensics: {repo}                             │
│  {days} days analyzed • Generated {date}            │
├─────────────────────────────────────────────────────┤
│  [Hotspots]  [Table]  [Coupling]                    │
├─────────────────────────────────────────────────────┤
│                                                     │
│   Zoomable Plotly.js Treemap                        │
│   - Size = lines_changed                            │
│   - Color = hotspot_score (green→yellow→red)        │
│   - Click to drill into directories                 │
│                                                     │
└─────────────────────────────────────────────────────┘
```

## Technology

- **Plotly.js** via CDN (~3MB) - treemap with built-in zoom
- **Vanilla JS** for tab switching (~15 lines)
- **Static HTML** - no server required, shareable as file

## Data Transformation

Transform flat file list to Plotly hierarchical format:

```python
def build_treemap_data(files: list[FileForensics]) -> dict:
    """
    Input: [{"path": "src/auth/login.py", "lines_changed": 200, "hotspot_score": 5000}, ...]
    Output: {
        "labels": ["", "src", "auth", "login.py", ...],
        "parents": ["", "", "src", "auth", ...],
        "values": [0, 0, 0, 200, ...],  # lines_changed for files, 0 for dirs
        "colors": [0, 0, 0, 5000, ...],  # hotspot_score
        "customdata": [{commits, authors, coupling}, ...]  # for tooltips
    }
    """
```

## Tab Structure

1. **Hotspots** (default) - Zoomable treemap
2. **Table** - Existing detailed table view
3. **Coupling** - Placeholder for BBU-ex2p (temporal coupling graph)

## Interactivity

- **Hover**: Tooltip with file details (path, hotspot, commits, authors, coupling)
- **Click directory**: Zoom into that directory
- **Breadcrumb**: Navigate back up the tree
- **Color scale**: Green (low) → Yellow (medium) → Red (high hotspot)

## Testing

**Python unit tests:**
- `build_treemap_data()` correctly transforms paths to hierarchy
- `generate_html_report()` includes Plotly CDN, tab structure, embedded data

**Manual browser test:**
```bash
bbu analyze-repo --output=html > report.html && open report.html
```

## Implementation Tasks

1. Add `build_treemap_data()` function in `visualization/treemap.py`
2. Update `html.py` to tabbed template with Plotly
3. Embed treemap data as JSON in HTML
4. Add tab switching JS
5. Update existing HTML tests

## Future

- Claude Code Chrome plugin for visual regression testing
- BBU-ex2p: Temporal coupling graph in Coupling tab
