# Temporal Coupling Graph Design

**Issue**: BBU-ex2p
**Date**: 2026-01-25

## Overview

Network graph visualization showing files that change together, based on Adam Tornhill's temporal coupling analysis from "Your Code as a Crime Scene".

## Key Insight

Cross-module coupling (files from different directories changing together) reveals hidden dependencies and potential architectural issues. The visualization highlights these with red edges.

## Technical Decisions

| Aspect | Decision | Rationale |
|--------|----------|-----------|
| Library | Cytoscape.js | Specialized for network graphs, better layouts than Plotly |
| Layout | `cose` | Force-directed, naturally clusters coupled files |
| Node color | By directory | Reveals cross-module coupling visually |
| Edge highlight | Red for cross-module | Draws attention to hidden dependencies |
| Interactivity | Pan/zoom + hover | Simple, sufficient for exploration |

## Architecture

```
AnalysisResult.files[].coupled_with
    → build_coupling_graph_data()
    → JSON embedded in HTML
    → Cytoscape.js renders
```

## Data Format

```python
{
    "nodes": [
        {"data": {"id": "src/auth.py", "label": "auth.py", "churn": 2000, "directory": "src"}}
    ],
    "edges": [
        {"data": {"source": "src/auth.py", "target": "tests/test_auth.py", "coupling": 0.65, "crossModule": true}}
    ],
    "directories": ["src", "tests"],
    "maxChurn": 2000
}
```

## Visual Design

**Nodes:**
- Size: Proportional to churn (hotspot score)
- Color: Assigned by top-level directory
- Label: Filename only (full path on hover)

**Edges:**
- Width + opacity: Proportional to coupling ratio
- Color: Gray (same directory), Red (cross-directory)

## Files to Modify

| File | Change |
|------|--------|
| `visualization/coupling_graph.py` | New - `build_coupling_graph_data()` |
| `visualization/html.py` | Add Cytoscape CDN, replace placeholder |
| `tests/.../test_coupling_graph.py` | New - unit tests |
| `tests/.../test_html.py` | Add integration tests |

## Test Plan

1. `test_empty_files_returns_empty_graph`
2. `test_files_without_coupling_returns_nodes_only`
3. `test_node_contains_required_fields`
4. `test_edge_contains_required_fields`
5. `test_coupling_creates_edge`
6. `test_cross_module_flag_true_for_different_directories`
7. `test_cross_module_flag_false_for_same_directory`
8. `test_edges_deduplicated`
9. `test_max_churn_calculated`
10. `test_root_level_file_directory`

## Edge Cases

| Case | Handling |
|------|----------|
| No coupling data | Empty graph with "No coupling detected" message |
| Coupled target not in files list | Create node for it anyway |
| Root-level files | directory = "root" |
| Same filename in different dirs | Full path as id, filename as label |
