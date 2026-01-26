# Coupling Graph Redesign

**Date**: 2026-01-26
**Status**: Approved
**Problem**: Current coupling visualization is an unreadable "squashed colored mess" with no obvious meaning

## Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Default view | Top 10 edges | Always readable, adapts to any codebase |
| Filtering approach | Top N (not %) | Intuitive, always shows something useful |
| Controls | Slider + directory focus | Simple UI, natural drill-down |
| Focus behavior | Highlight (dim others) | Keeps context visible |

## Default View

Show only the 10 strongest coupling relationships, ranked by coupling ratio.

**Visual encoding:**
- Edge color: Red = cross-module, gray = intra-module
- Edge thickness: Proportional to coupling strength
- Node color: By directory (existing)
- Node size: Fixed

**Empty state**: If fewer than 10 edges exist, show all with message: "Showing all N coupling relationships (threshold: 30%)"

## Interactive Controls

### Slider
- Label: "Show top N edges"
- Range: 10 to 100 (or max available)
- Default: 10
- Position: Above graph
- Live update on change

### Directory Focus
On node click:
1. Clicked node + connected nodes stay fully visible
2. Other nodes/edges dim to 20% opacity
3. "Clear focus" button appears (or click empty space to reset)
4. Slider still works while focused

**Visual feedback:**
- Pointer cursor on node hover
- Highlight ring on focused node
- Tooltip: filename, directory, churn score, coupling count

## Data Changes

### Backend (coupling_graph.py)
- Sort edges by coupling ratio descending
- Only include nodes that appear in edges
- Add `totalEdges` field for slider max

```python
{
    "nodes": [...],       # Only nodes with edges
    "edges": [...],       # Sorted by coupling desc
    "directories": [...],
    "maxChurn": int,
    "totalEdges": int,    # Total available for slider
}
```

### Frontend (html.py)
- Receive full edge dataset
- JS handles top-N filtering (no backend round-trips)
- Slider controls displayed subset

## Implementation

### Files to modify

| File | Changes |
|------|---------|
| `coupling_graph.py` | Sort edges, add totalEdges |
| `html.py` | Slider UI, focus handler, dim/highlight, tooltip |
| `test_coupling_graph.py` | Test sorting, totalEdges |
| `test_html.py` | Test slider markup, JS functions |

### JavaScript functions
- `filterTopN(n)` - Show only top N edges, hide orphan nodes
- `focusNode(nodeId)` - Dim unconnected elements to 20%
- `clearFocus()` - Restore full opacity
- Slider event listener
- Node click handler

### UI Layout
```
[Show top [===10===] edges]  [Clear focus]
+----------------------------------------+
|                                        |
|           Coupling Graph               |
|                                        |
+----------------------------------------+
```
