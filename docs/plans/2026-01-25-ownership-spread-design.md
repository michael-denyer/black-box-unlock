# Ownership Spread Detection Design

**Task:** BBU-k4e2 - Calculate ownership spread per file
**Date:** 2026-01-25

## Summary

Count unique authors per file from git history. Files with >3 authors and high churn indicate coordination risk and knowledge diffusion.

## Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Data source | Reuse gmap JSON | Already includes author_email per commit |
| Author identifier | author_email | More stable than author_name |
| High risk threshold | >3 authors | Standard threshold for coordination overhead |
| Storage type | list[str] for authors | Pydantic doesn't support set, dedupe in function |

## Data Model

```python
class FileOwnership(BaseModel):
    """Ownership metrics for a single file."""

    path: str
    authors: list[str]  # unique author emails
    commits: int

    @property
    def author_count(self) -> int:
        """Number of unique authors."""
        return len(self.authors)

    @property
    def is_high_risk(self) -> bool:
        """Files with >3 authors are coordination risks."""
        return self.author_count > 3
```

## Algorithm

```python
def calculate_file_ownership(
    gmap_data: dict[str, Any],
) -> list[FileOwnership]:
    """
    1. Iterate through gmap entries
    2. For each file in each commit, add author_email to file's author set
    3. Track commit count per file
    4. Convert sets to sorted lists for Pydantic
    """
```

Complexity: O(entries × files) - single pass through data.

## Test Strategy

| Test | Purpose |
|------|---------|
| Model creation | FileOwnership with path, authors, commits |
| author_count property | Returns len(authors) |
| is_high_risk property | True when >3 authors |
| Single author file | 1 author across multiple commits |
| Multiple authors | Same file, different authors |
| Empty data | Returns empty list |
| Integration | Run on this repo |
