# CI/CD Build Failures Design

Track build failures per file to identify fragile code.

## Overview

Extract failed workflow runs from GitHub Actions via `gh` CLI, link failures to files changed in the triggering commit, and display both per-file metrics and a dedicated CI overview tab.

## Data Model

```python
# New models in cicd/models.py
class WorkflowRun(BaseModel):
    """A GitHub Actions workflow run."""
    run_id: int
    workflow_name: str
    commit_sha: str
    conclusion: str  # "success", "failure", "timed_out", etc.
    created_at: datetime

class BuildFailure(BaseModel):
    """A CI workflow run that failed."""
    run_id: int
    workflow_name: str
    commit_sha: str
    files_changed: list[str]
    failed_at: datetime
    conclusion: str

# Additions to FileForensics in core/models.py
class FileForensics(BaseModel):
    # ... existing fields ...
    build_failures: int = 0      # Count of failed runs touching this file
    failure_rate: float = 0.0    # failures / total runs touching file
```

## Data Extraction

```python
# cicd/github_actions.py

def fetch_workflow_runs(
    repo_path: Path,
    since_days: int = 30,
    workflow: str | None = None,
) -> list[WorkflowRun]:
    """Fetch workflow runs via gh CLI.

    Command: gh run list --json conclusion,headSha,workflowName,createdAt,databaseId
    """

def get_failed_runs(runs: list[WorkflowRun]) -> list[BuildFailure]:
    """Filter to failed runs and enrich with files changed.

    For each failed run:
    1. Get commit SHA from run
    2. Run: git show --name-only <sha> to get files changed
    3. Build BuildFailure with file list
    """

def calculate_file_failure_stats(
    failures: list[BuildFailure],
    total_runs_per_file: dict[str, int],
) -> dict[str, FileFailureStats]:
    """Aggregate failures per file."""
```

Flow: `gh run list` → filter failures → `git show` for files → aggregate per file.

## CI Overview Tab

New "CI/CD" tab in HTML report:

1. **Summary cards**:
   - Total runs / Failed runs / Success rate
   - Most failure-prone files (top 5)

2. **Failure timeline** (Plotly bar chart):
   - X-axis: dates over analysis period
   - Y-axis: failure count per day
   - Color: red for failures

3. **File failure table**:
   - Columns: File, Failures, Total Runs, Failure Rate
   - Sorted by failure count descending

## CLI Integration

```bash
bbu analyze-repo --days=30  # Includes CI data if gh available
bbu analyze-repo --no-ci    # Skip CI analysis
```

## Graceful Degradation

- `gh` CLI not available → skip CI analysis, log warning
- Not authenticated → skip, suggest `gh auth login`
- No workflow runs → show empty CI tab with message

## File Structure

```
src/black_box_unlock/cicd/
├── __init__.py
├── github_actions.py   # gh CLI wrapper + parsing
└── models.py           # BuildFailure, WorkflowRun models
```

## Testing

- Unit tests: Mock `gh run list` JSON output
- Integration tests: `@pytest.mark.requires_gh` marker
- Test graceful degradation when gh unavailable

## Future Enhancements

- Log parsing for specific test failures (more precise attribution)
- GitHub MCP integration when available
- Support for other CI platforms (GitLab CI, Jenkins)
