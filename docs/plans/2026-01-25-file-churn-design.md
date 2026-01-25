# File Churn Extraction Design

**Task:** BBU-8b03 - Extract file churn from git log
**Date:** 2026-01-25

## Summary

Extract file churn metrics (commits, lines changed per file) using gmap for performance, with git subprocess fallback.

## Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Parsing approach | gmap CLI | SQLite cache, parallel processing, JSON output |
| Fallback | git subprocess | Zero-dep option when gmap unavailable |
| Time filtering | `--since` flag | Let git/gmap filter efficiently |

## Data Model

```python
class FileChurn(BaseModel):
    path: str
    commits: int
    lines_added: int
    lines_deleted: int
    first_commit: datetime
    last_commit: datetime

    @property
    def total_lines_changed(self) -> int:
        return self.lines_added + self.lines_deleted
```

## Architecture

```
src/black_box_unlock/
├── core/
│   ├── models.py          # FileChurn model
│   └── exceptions.py      # NotAGitRepoError, etc.
└── git/
    └── churn.py           # extract_file_churn()
```

## Implementation

```python
def extract_file_churn(repo_path: Path, since_days: int = 30) -> list[FileChurn]:
    """Extract file churn. Uses gmap if available, falls back to git."""

    if not (repo_path / ".git").exists():
        raise NotAGitRepoError(f"Not a git repository: {repo_path}")

    try:
        return _extract_with_gmap(repo_path, since_days)
    except FileNotFoundError:
        warnings.warn("gmap not found, using slower git parsing", stacklevel=2)
        return _extract_with_git(repo_path, since_days)
```

## Test Strategy

| Test Type | Location | Coverage |
|-----------|----------|----------|
| Model validation | `tests/unit/core/test_models.py` | FileChurn valid/invalid |
| gmap parsing | `tests/unit/git/test_churn.py` | JSON fixture parsing |
| Fallback | `tests/unit/git/test_churn.py` | Warning when gmap missing |
| Error cases | `tests/unit/git/test_churn.py` | NotAGitRepoError |
| Integration | `tests/integration/test_git_churn.py` | Real repo analysis |

## Dependencies

- `gmap` (optional, Rust binary) - `cargo install gmap`
- `git` (required) - system dependency
