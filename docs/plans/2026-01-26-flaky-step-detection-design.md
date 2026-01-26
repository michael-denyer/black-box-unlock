# Flaky Step Detection Design

**Issue**: BBU-pvcw
**Date**: 2026-01-26
**Status**: Approved

## Overview

Detect CI steps that fail intermittently (flaky) by analyzing GitHub Actions re-run patterns. A step is flaky if it fails on attempt N but passes on attempt N+1 for the same commit.

## Scope

**In scope**: Step-level flakiness detection using structured GitHub API data.

**Out of scope** (tracked separately):
- BBU-deb: JUnit XML artifact parsing for test-level granularity
- BBU-tcl: Pytest log parsing for test-level granularity
- BBU-eao: Batch API fetching optimization

## Data Model

```python
# src/black_box_unlock/cicd/models.py

class StepResult(BaseModel):
    """A single step execution within a job."""
    job_name: str           # "test (3.10)"
    step_name: str          # "Run tests"
    conclusion: str         # "success", "failure", "skipped"
    run_id: int
    attempt: int            # 1, 2, 3... for re-runs
    commit_sha: str
    executed_at: datetime

class FlakyStep(BaseModel):
    """Aggregated flakiness data for a job/step combination."""
    job_name: str
    step_name: str
    first_seen: datetime
    last_seen: datetime
    total_runs: int
    failures: int
    flaky_count: int        # Times it failed then passed on retry

    @property
    def flaky_rate(self) -> float:
        return self.flaky_count / self.total_runs if self.total_runs else 0.0

    @property
    def is_active(self) -> bool:
        """Step ran in last 7 days."""
        return (datetime.now(UTC) - self.last_seen).days <= 7
```

## Data Fetching

Uses GitHub REST API via `gh api`:

1. **List runs**: `GET /repos/{owner}/{repo}/actions/runs?per_page=100` (1 call)
2. **Get jobs+steps**: `GET /repos/{owner}/{repo}/actions/runs/{id}/jobs` (N calls)

```python
# src/black_box_unlock/cicd/github_actions.py

def fetch_all_runs(limit: int = 100) -> list[dict]:
    """Fetch workflow runs via REST API."""
    result = subprocess.run(
        ["gh", "api", f"/repos/{{owner}}/{{repo}}/actions/runs?per_page={limit}"],
        capture_output=True, text=True, check=True
    )
    return json.loads(result.stdout)["workflow_runs"]

def fetch_jobs_for_run(run_id: int) -> list[dict]:
    """Fetch jobs+steps for a single run."""
    result = subprocess.run(
        ["gh", "api", f"/repos/{{owner}}/{{repo}}/actions/runs/{run_id}/jobs"],
        capture_output=True, text=True, check=True
    )
    return json.loads(result.stdout)["jobs"]
```

Note: This is N+1 API calls. See BBU-eao for optimization investigation.

## Detection Logic

```python
def detect_flaky_steps(runs: list[dict]) -> list[FlakyStep]:
    """Detect flaky steps by analyzing re-run patterns."""
    # 1. Group runs by (head_sha, workflow) to find re-runs
    # 2. Sort each group by attempt number
    # 3. For each failed step, check if next attempt passed
    # 4. Aggregate stats per (job_name, step_name)
    # 5. Return steps with flaky_count > 0 or high failure rate
```

**Flaky definition**: Same commit SHA, step failed on attempt N, passed on attempt N+1.

## Integration

Add `flaky_steps: list[FlakyStep]` to `AnalysisResult` in `analysis.py`.

Fetched alongside existing CI data when `include_ci=True`. Failures caught and ignored (CI data is optional).

## Output

**JSON**: Adds `flaky_steps` array to output.

**HTML**: Future enhancement - add "Flaky Steps" tab/section.

## Testing Strategy

1. Unit tests with mocked `gh api` responses
2. Test flaky detection logic with synthetic run data
3. Integration test with `@pytest.mark.requires_gh` marker
