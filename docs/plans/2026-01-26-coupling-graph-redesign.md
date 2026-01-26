# Coupling Graph Redesign Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make coupling graph readable by showing top N edges with interactive filtering and focus.

**Architecture:** Backend sorts edges by coupling ratio and adds totalEdges count. Frontend receives full dataset and uses JS to filter to top N, with slider control and click-to-focus interaction.

**Tech Stack:** Python (Pydantic models), Cytoscape.js, vanilla JS

---

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

---

## Implementation Tasks

### Task 1: Backend - Sort edges and add totalEdges

**Files:**
- Modify: `src/black_box_unlock/visualization/coupling_graph.py:40-98`
- Test: `tests/unit/visualization/test_coupling_graph.py`

**Step 1: Write failing test for sorted edges**

Add to `tests/unit/visualization/test_coupling_graph.py`:

```python
def test_edges_sorted_by_coupling_descending(self):
    """Edges are sorted by coupling ratio, highest first."""
    files = [
        FileForensics(
            path="src/auth.py",
            commits=10,
            lines_changed=200,
            authors=["alice@example.com"],
            coupled_with=[
                CouplingInfo(file="src/low.py", ratio=0.35),
                CouplingInfo(file="src/high.py", ratio=0.90),
                CouplingInfo(file="src/mid.py", ratio=0.55),
            ],
        )
    ]

    result = build_coupling_graph_data(files)

    couplings = [e["data"]["coupling"] for e in result["edges"]]
    assert couplings == [0.90, 0.55, 0.35]
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/visualization/test_coupling_graph.py::TestBuildCouplingGraphData::test_edges_sorted_by_coupling_descending -v`
Expected: FAIL (edges not sorted)

**Step 3: Implement edge sorting**

In `coupling_graph.py`, after building edges list (line 91), add:

```python
    edges.sort(key=lambda e: e["data"]["coupling"], reverse=True)
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/visualization/test_coupling_graph.py::TestBuildCouplingGraphData::test_edges_sorted_by_coupling_descending -v`
Expected: PASS

**Step 5: Write failing test for totalEdges field**

Add to `tests/unit/visualization/test_coupling_graph.py`:

```python
def test_total_edges_field_present(self):
    """Result includes totalEdges count for slider max."""
    files = [
        FileForensics(
            path="src/auth.py",
            commits=10,
            lines_changed=200,
            authors=["alice@example.com"],
            coupled_with=[
                CouplingInfo(file="src/a.py", ratio=0.5),
                CouplingInfo(file="src/b.py", ratio=0.6),
                CouplingInfo(file="src/c.py", ratio=0.7),
            ],
        )
    ]

    result = build_coupling_graph_data(files)

    assert result["totalEdges"] == 3
```

**Step 6: Run test to verify it fails**

Run: `uv run pytest tests/unit/visualization/test_coupling_graph.py::TestBuildCouplingGraphData::test_total_edges_field_present -v`
Expected: FAIL (KeyError: totalEdges)

**Step 7: Add totalEdges to return dict**

In `coupling_graph.py`, update the return statement:

```python
    return {
        "nodes": list(nodes.values()),
        "edges": edges,
        "directories": sorted(directories),
        "maxChurn": max_churn,
        "totalEdges": len(edges),
    }
```

Also update empty case return at line 51:

```python
        return {"nodes": [], "edges": [], "directories": [], "maxChurn": 0, "totalEdges": 0}
```

**Step 8: Run test to verify it passes**

Run: `uv run pytest tests/unit/visualization/test_coupling_graph.py -v`
Expected: All tests PASS

**Step 9: Commit**

```bash
git add src/black_box_unlock/visualization/coupling_graph.py tests/unit/visualization/test_coupling_graph.py
git commit -m "feat(coupling): sort edges by coupling ratio, add totalEdges"
```

---

### Task 2: Frontend - Add slider control UI

**Files:**
- Modify: `src/black_box_unlock/visualization/html.py:320-323`
- Test: `tests/unit/visualization/test_html.py`

**Step 1: Write failing test for slider markup**

Add to `tests/unit/visualization/test_html.py`:

```python
def test_coupling_slider_present(sample_result):
    """Coupling tab has slider control for top N edges."""
    html = generate_html_report(sample_result)

    assert 'id="edge-slider"' in html
    assert 'id="edge-count"' in html
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/visualization/test_html.py::test_coupling_slider_present -v`
Expected: FAIL

**Step 3: Add slider HTML**

In `html.py`, update the coupling tab content (around line 320):

```html
        <div id="coupling" class="tab-content">
            <div class="coupling-controls">
                <label>Show top <input type="range" id="edge-slider" min="10" max="100" value="10"> <span id="edge-count">10</span> edges</label>
                <button id="clear-focus" style="display: none;">Clear focus</button>
            </div>
            <div class="coupling-legend" id="coupling-legend"></div>
            <div id="coupling-graph"></div>
        </div>
```

**Step 4: Add CSS for controls**

Add to the style section (around line 110):

```css
        .coupling-controls {{
            padding: 10px 20px;
            display: flex;
            align-items: center;
            gap: 20px;
            background: var(--card-bg);
            border-bottom: 1px solid var(--border);
        }}
        .coupling-controls label {{
            display: flex;
            align-items: center;
            gap: 8px;
            font-size: 14px;
        }}
        .coupling-controls input[type="range"] {{
            width: 150px;
        }}
        #clear-focus {{
            padding: 4px 12px;
            border: 1px solid var(--border);
            border-radius: 4px;
            background: var(--bg);
            cursor: pointer;
        }}
```

**Step 5: Run test to verify it passes**

Run: `uv run pytest tests/unit/visualization/test_html.py::test_coupling_slider_present -v`
Expected: PASS

**Step 6: Commit**

```bash
git add src/black_box_unlock/visualization/html.py tests/unit/visualization/test_html.py
git commit -m "feat(coupling): add slider control UI"
```

---

### Task 3: Frontend - Implement filterTopN function

**Files:**
- Modify: `src/black_box_unlock/visualization/html.py:440-510`
- Test: `tests/unit/visualization/test_html.py`

**Step 1: Write failing test for filterTopN function**

Add to `tests/unit/visualization/test_html.py`:

```python
def test_filter_top_n_function_present(sample_result):
    """JavaScript includes filterTopN function."""
    html = generate_html_report(sample_result)

    assert "function filterTopN(" in html
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/visualization/test_html.py::test_filter_top_n_function_present -v`
Expected: FAIL

**Step 3: Add filterTopN and update initCouplingGraph**

Replace the initCouplingGraph function in `html.py`. See implementation section below for full code.

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/visualization/test_html.py::test_filter_top_n_function_present -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/black_box_unlock/visualization/html.py tests/unit/visualization/test_html.py
git commit -m "feat(coupling): implement filterTopN for top-N edge display"
```

---

### Task 4: Frontend - Implement focus/unfocus interaction

**Files:**
- Modify: `src/black_box_unlock/visualization/html.py`
- Test: `tests/unit/visualization/test_html.py`

**Step 1: Write failing test for focus functions**

Add to `tests/unit/visualization/test_html.py`:

```python
def test_focus_functions_present(sample_result):
    """JavaScript includes focusNode and clearFocus functions."""
    html = generate_html_report(sample_result)

    assert "function focusNode(" in html
    assert "function clearFocus(" in html
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/visualization/test_html.py::test_focus_functions_present -v`
Expected: FAIL

**Step 3: Add focusNode and clearFocus functions**

See implementation section below for full code.

**Step 4: Add click handlers in initCouplingGraph**

Add node click, background click, and clear button handlers.

**Step 5: Run test to verify it passes**

Run: `uv run pytest tests/unit/visualization/test_html.py::test_focus_functions_present -v`
Expected: PASS

**Step 6: Run all tests**

Run: `uv run pytest -v`
Expected: All tests PASS

**Step 7: Commit**

```bash
git add src/black_box_unlock/visualization/html.py tests/unit/visualization/test_html.py
git commit -m "feat(coupling): implement click-to-focus interaction"
```

---

### Task 5: Add tooltip on hover

**Files:**
- Modify: `src/black_box_unlock/visualization/html.py`
- Test: `tests/unit/visualization/test_html.py`

**Step 1: Write failing test for tooltip**

Add to `tests/unit/visualization/test_html.py`:

```python
def test_tooltip_element_present(sample_result):
    """Coupling tab has tooltip element."""
    html = generate_html_report(sample_result)

    assert 'id="coupling-tooltip"' in html
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/visualization/test_html.py::test_tooltip_element_present -v`
Expected: FAIL

**Step 3: Add tooltip HTML, CSS, and JS**

Add tooltip div, styling, and showTooltip/hideTooltip functions.
Note: Use textContent or safe DOM methods instead of innerHTML for tooltip content.

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/visualization/test_html.py::test_tooltip_element_present -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/black_box_unlock/visualization/html.py tests/unit/visualization/test_html.py
git commit -m "feat(coupling): add tooltip on node hover"
```

---

### Task 6: Final integration test

**Files:**
- Test: Manual browser test

**Step 1: Generate test report**

Run: `uv run bbu analyze-repo --days=90 --output=test-report.html`

**Step 2: Open in browser and verify**

- [ ] Slider shows "Show top 10 edges" by default
- [ ] Moving slider changes visible edges
- [ ] Clicking node dims unconnected nodes/edges
- [ ] Clear focus button appears and works
- [ ] Hovering node shows tooltip
- [ ] Cross-module edges are red, intra-module are gray

**Step 3: Close beads issue**

```bash
bd close BBU-3r7
bd sync
```

**Step 4: Final commit and push**

```bash
git push
```
