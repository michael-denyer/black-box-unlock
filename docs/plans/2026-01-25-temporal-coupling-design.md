# Temporal Coupling Detection Design

**Task:** BBU-f3v2 - Detect temporal coupling from commits
**Date:** 2026-01-25

## Summary

Detect files that change together frequently (>30% of the time) to identify hidden dependencies.

## Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Data source | Reuse gmap JSON | Already fetched for churn, no extra git calls |
| Coupling formula | `co_changes / min(commits_a, commits_b)` | Tornhill's method - catches dependencies even when one file is more active |
| Threshold | 30% default | Standard threshold for "meaningful" coupling |
| Pair ordering | Alphabetical (file_a < file_b) | Avoid duplicate pairs |

## Data Model

```python
class TemporalCoupling(BaseModel):
    """Two files that change together frequently."""

    file_a: str
    file_b: str
    co_change_count: int
    commits_a: int
    commits_b: int

    @property
    def coupling_ratio(self) -> float:
        """Ratio based on min commits (Tornhill's formula)."""
        return self.co_change_count / min(self.commits_a, self.commits_b)
```

## Algorithm

```python
def detect_temporal_coupling(
    gmap_data: dict,
    min_ratio: float = 0.3,
) -> list[TemporalCoupling]:
    """
    1. Build commit→files mapping from gmap entries
    2. Count per-file commits
    3. For each commit with 2+ files, count all pairs
    4. Calculate coupling ratio for each pair
    5. Filter by min_ratio threshold
    """
```

Complexity: O(commits × files²) worst case, typically low.

## Coupling Ratio Formula

```
coupling_ratio = co_change_count / min(commits_a, commits_b)
```

Example:
- File A changed 10 times
- File B changed 5 times
- They changed together 4 times
- Coupling = 4 / min(10, 5) = 4/5 = **80%**

This answers: "When the less-frequently-changed file changes, does the other change too?"

## Test Strategy

| Test | Purpose |
|------|---------|
| Coupling calculation | 2 files in 2 commits → 100% |
| Threshold filtering | Pairs below 30% excluded |
| Alphabetical ordering | (B, A) normalized to (A, B) |
| Single-file commits | No pairs generated |
| Empty data | Returns empty list |
| Integration | Run on real repo |
