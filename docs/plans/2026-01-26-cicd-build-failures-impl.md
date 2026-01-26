# CI/CD Build Failures Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Track build failures per file to identify fragile code via GitHub Actions.

**Architecture:** New `cicd/` module with `gh` CLI wrapper. Fetch failed runs, link to files via commit SHA, aggregate per-file failure counts. Add to FileForensics model and new CI tab in HTML report.

**Tech Stack:** Python, Pydantic, subprocess (gh CLI), Plotly (visualization)

---

## Task 1: Create CI/CD Models

**Files:**
- Create: `src/black_box_unlock/cicd/__init__.py`
- Create: `src/black_box_unlock/cicd/models.py`
- Test: `tests/unit/cicd/test_models.py`

**Step 1: Create test directory and test file**

```bash
mkdir -p tests/unit/cicd
```

**Step 2: Write the failing tests**

Create `tests/unit/cicd/test_models.py`:

```python
"""Tests for CI/CD data models."""

from datetime import datetime, timezone

import pytest

from black_box_unlock.cicd.models import BuildFailure, WorkflowRun


class TestWorkflowRun:
    """Tests for WorkflowRun model."""

    def test_creates_workflow_run_with_required_fields(self):
        """Creates WorkflowRun with all required fields."""
        run = WorkflowRun(
            run_id=123,
            workflow_name="CI",
            commit_sha="abc123",
            conclusion="success",
            created_at=datetime(2026, 1, 26, tzinfo=timezone.utc),
        )
        assert run.run_id == 123
        assert run.workflow_name == "CI"
        assert run.commit_sha == "abc123"
        assert run.conclusion == "success"

    def test_is_failure_returns_true_for_failure_conclusion(self):
        """is_failure returns True when conclusion is 'failure'."""
        run = WorkflowRun(
            run_id=1,
            workflow_name="CI",
            commit_sha="abc",
            conclusion="failure",
            created_at=datetime.now(timezone.utc),
        )
        assert run.is_failure is True

    def test_is_failure_returns_false_for_success(self):
        """is_failure returns False when conclusion is 'success'."""
        run = WorkflowRun(
            run_id=1,
            workflow_name="CI",
            commit_sha="abc",
            conclusion="success",
            created_at=datetime.now(timezone.utc),
        )
        assert run.is_failure is False


class TestBuildFailure:
    """Tests for BuildFailure model."""

    def test_creates_build_failure_with_files_changed(self):
        """Creates BuildFailure with list of files changed."""
        failure = BuildFailure(
            run_id=456,
            workflow_name="CI",
            commit_sha="def456",
            files_changed=["src/main.py", "tests/test_main.py"],
            failed_at=datetime(2026, 1, 26, tzinfo=timezone.utc),
            conclusion="failure",
        )
        assert failure.run_id == 456
        assert len(failure.files_changed) == 2
        assert "src/main.py" in failure.files_changed
```

**Step 3: Run tests to verify they fail**

```bash
uv run pytest tests/unit/cicd/test_models.py -v
```

Expected: FAIL with "ModuleNotFoundError: No module named 'black_box_unlock.cicd'"

**Step 4: Create the cicd package**

Create `src/black_box_unlock/cicd/__init__.py`:

```python
"""CI/CD forensics module."""
```

Create `src/black_box_unlock/cicd/models.py`:

```python
"""CI/CD data models."""

from datetime import datetime

from pydantic import BaseModel


class WorkflowRun(BaseModel):
    """A GitHub Actions workflow run."""

    run_id: int
    workflow_name: str
    commit_sha: str
    conclusion: str  # "success", "failure", "timed_out", "cancelled", etc.
    created_at: datetime

    @property
    def is_failure(self) -> bool:
        """Check if this run failed."""
        return self.conclusion in ("failure", "timed_out")


class BuildFailure(BaseModel):
    """A CI workflow run that failed, with files changed."""

    run_id: int
    workflow_name: str
    commit_sha: str
    files_changed: list[str]
    failed_at: datetime
    conclusion: str
```

**Step 5: Run tests to verify they pass**

```bash
uv run pytest tests/unit/cicd/test_models.py -v
```

Expected: PASS (3 tests)

**Step 6: Commit**

```bash
git add src/black_box_unlock/cicd/ tests/unit/cicd/
git commit -m "feat(cicd): add WorkflowRun and BuildFailure models"
```

---

## Task 2: Fetch Workflow Runs via gh CLI

**Files:**
- Create: `src/black_box_unlock/cicd/github_actions.py`
- Test: `tests/unit/cicd/test_github_actions.py`

**Step 1: Write the failing tests**

Create `tests/unit/cicd/test_github_actions.py`:

```python
"""Tests for GitHub Actions CI/CD integration."""

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from black_box_unlock.cicd.github_actions import (
    fetch_workflow_runs,
    parse_workflow_runs,
)
from black_box_unlock.cicd.models import WorkflowRun


class TestParseWorkflowRuns:
    """Tests for parsing gh CLI JSON output."""

    def test_parses_successful_run(self):
        """Parses a successful workflow run from JSON."""
        gh_json = [
            {
                "databaseId": 123,
                "workflowName": "CI",
                "headSha": "abc123def",
                "conclusion": "success",
                "createdAt": "2026-01-26T10:00:00Z",
            }
        ]
        runs = parse_workflow_runs(gh_json)
        assert len(runs) == 1
        assert runs[0].run_id == 123
        assert runs[0].workflow_name == "CI"
        assert runs[0].commit_sha == "abc123def"
        assert runs[0].conclusion == "success"

    def test_parses_failed_run(self):
        """Parses a failed workflow run from JSON."""
        gh_json = [
            {
                "databaseId": 456,
                "workflowName": "Tests",
                "headSha": "def456ghi",
                "conclusion": "failure",
                "createdAt": "2026-01-26T11:00:00Z",
            }
        ]
        runs = parse_workflow_runs(gh_json)
        assert len(runs) == 1
        assert runs[0].is_failure is True

    def test_parses_multiple_runs(self):
        """Parses multiple workflow runs."""
        gh_json = [
            {
                "databaseId": 1,
                "workflowName": "CI",
                "headSha": "aaa",
                "conclusion": "success",
                "createdAt": "2026-01-26T10:00:00Z",
            },
            {
                "databaseId": 2,
                "workflowName": "CI",
                "headSha": "bbb",
                "conclusion": "failure",
                "createdAt": "2026-01-26T11:00:00Z",
            },
        ]
        runs = parse_workflow_runs(gh_json)
        assert len(runs) == 2

    def test_empty_list_returns_empty(self):
        """Empty JSON list returns empty result."""
        runs = parse_workflow_runs([])
        assert runs == []


class TestFetchWorkflowRuns:
    """Tests for fetching runs via gh CLI."""

    @patch("black_box_unlock.cicd.github_actions.subprocess.run")
    def test_calls_gh_with_correct_args(self, mock_run):
        """Calls gh run list with correct JSON fields."""
        mock_run.return_value = MagicMock(
            stdout="[]",
            returncode=0,
        )
        fetch_workflow_runs(limit=50)

        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert "gh" in args
        assert "run" in args
        assert "list" in args
        assert "--json" in args

    @patch("black_box_unlock.cicd.github_actions.subprocess.run")
    def test_returns_parsed_workflow_runs(self, mock_run):
        """Returns list of WorkflowRun objects."""
        gh_output = json.dumps([
            {
                "databaseId": 999,
                "workflowName": "CI",
                "headSha": "xyz",
                "conclusion": "success",
                "createdAt": "2026-01-26T12:00:00Z",
            }
        ])
        mock_run.return_value = MagicMock(stdout=gh_output, returncode=0)

        runs = fetch_workflow_runs(limit=10)
        assert len(runs) == 1
        assert isinstance(runs[0], WorkflowRun)
        assert runs[0].run_id == 999
```

**Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/unit/cicd/test_github_actions.py -v
```

Expected: FAIL with "ImportError: cannot import name 'fetch_workflow_runs'"

**Step 3: Implement the functions**

Create `src/black_box_unlock/cicd/github_actions.py`:

```python
"""GitHub Actions CI/CD integration via gh CLI."""

import json
import subprocess
from datetime import datetime

from .models import BuildFailure, WorkflowRun


def parse_workflow_runs(gh_json: list[dict]) -> list[WorkflowRun]:
    """Parse gh run list JSON output into WorkflowRun objects.

    Args:
        gh_json: List of dicts from gh run list --json output.

    Returns:
        List of WorkflowRun objects.
    """
    runs = []
    for item in gh_json:
        runs.append(
            WorkflowRun(
                run_id=item["databaseId"],
                workflow_name=item["workflowName"],
                commit_sha=item["headSha"],
                conclusion=item["conclusion"] or "unknown",
                created_at=datetime.fromisoformat(
                    item["createdAt"].replace("Z", "+00:00")
                ),
            )
        )
    return runs


def fetch_workflow_runs(limit: int = 100) -> list[WorkflowRun]:
    """Fetch recent workflow runs via gh CLI.

    Args:
        limit: Maximum number of runs to fetch.

    Returns:
        List of WorkflowRun objects.

    Raises:
        subprocess.CalledProcessError: If gh command fails.
    """
    cmd = [
        "gh",
        "run",
        "list",
        "--limit",
        str(limit),
        "--json",
        "databaseId,workflowName,headSha,conclusion,createdAt",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    gh_json = json.loads(result.stdout)
    return parse_workflow_runs(gh_json)
```

**Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/unit/cicd/test_github_actions.py -v
```

Expected: PASS (6 tests)

**Step 5: Commit**

```bash
git add src/black_box_unlock/cicd/github_actions.py tests/unit/cicd/test_github_actions.py
git commit -m "feat(cicd): add gh CLI wrapper for workflow runs"
```

---

## Task 3: Get Files Changed per Commit

**Files:**
- Modify: `src/black_box_unlock/cicd/github_actions.py`
- Test: `tests/unit/cicd/test_github_actions.py`

**Step 1: Add failing tests**

Add to `tests/unit/cicd/test_github_actions.py`:

```python
from black_box_unlock.cicd.github_actions import (
    fetch_workflow_runs,
    get_files_changed,
    parse_workflow_runs,
)


class TestGetFilesChanged:
    """Tests for getting files changed in a commit."""

    @patch("black_box_unlock.cicd.github_actions.subprocess.run")
    def test_returns_list_of_files(self, mock_run):
        """Returns list of files from git show output."""
        mock_run.return_value = MagicMock(
            stdout="src/main.py\ntests/test_main.py\n",
            returncode=0,
        )
        files = get_files_changed("abc123")
        assert files == ["src/main.py", "tests/test_main.py"]

    @patch("black_box_unlock.cicd.github_actions.subprocess.run")
    def test_filters_empty_lines(self, mock_run):
        """Filters out empty lines from output."""
        mock_run.return_value = MagicMock(
            stdout="src/main.py\n\n\n",
            returncode=0,
        )
        files = get_files_changed("abc123")
        assert files == ["src/main.py"]

    @patch("black_box_unlock.cicd.github_actions.subprocess.run")
    def test_calls_git_show_with_name_only(self, mock_run):
        """Calls git show with --name-only flag."""
        mock_run.return_value = MagicMock(stdout="", returncode=0)
        get_files_changed("abc123")

        args = mock_run.call_args[0][0]
        assert "git" in args
        assert "show" in args
        assert "--name-only" in args
        assert "abc123" in args
```

**Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/unit/cicd/test_github_actions.py::TestGetFilesChanged -v
```

Expected: FAIL with "ImportError: cannot import name 'get_files_changed'"

**Step 3: Implement get_files_changed**

Add to `src/black_box_unlock/cicd/github_actions.py`:

```python
def get_files_changed(commit_sha: str) -> list[str]:
    """Get list of files changed in a commit.

    Args:
        commit_sha: Git commit SHA.

    Returns:
        List of file paths changed in the commit.
    """
    cmd = [
        "git",
        "show",
        "--name-only",
        "--format=",  # Suppress commit info, only show files
        commit_sha,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    files = [f.strip() for f in result.stdout.strip().split("\n") if f.strip()]
    return files
```

**Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/unit/cicd/test_github_actions.py -v
```

Expected: PASS (9 tests)

**Step 5: Commit**

```bash
git add src/black_box_unlock/cicd/github_actions.py tests/unit/cicd/test_github_actions.py
git commit -m "feat(cicd): add get_files_changed for commit file lookup"
```

---

## Task 4: Build Failures with File Attribution

**Files:**
- Modify: `src/black_box_unlock/cicd/github_actions.py`
- Test: `tests/unit/cicd/test_github_actions.py`

**Step 1: Add failing tests**

Add to `tests/unit/cicd/test_github_actions.py`:

```python
from black_box_unlock.cicd.github_actions import (
    build_failures_from_runs,
    fetch_workflow_runs,
    get_files_changed,
    parse_workflow_runs,
)
from black_box_unlock.cicd.models import BuildFailure, WorkflowRun


class TestBuildFailuresFromRuns:
    """Tests for building failure objects with file attribution."""

    @patch("black_box_unlock.cicd.github_actions.get_files_changed")
    def test_creates_failure_for_failed_run(self, mock_get_files):
        """Creates BuildFailure for each failed run."""
        mock_get_files.return_value = ["src/broken.py"]
        runs = [
            WorkflowRun(
                run_id=1,
                workflow_name="CI",
                commit_sha="abc",
                conclusion="failure",
                created_at=datetime.now(timezone.utc),
            )
        ]
        failures = build_failures_from_runs(runs)
        assert len(failures) == 1
        assert failures[0].run_id == 1
        assert failures[0].files_changed == ["src/broken.py"]

    @patch("black_box_unlock.cicd.github_actions.get_files_changed")
    def test_skips_successful_runs(self, mock_get_files):
        """Does not create failures for successful runs."""
        runs = [
            WorkflowRun(
                run_id=1,
                workflow_name="CI",
                commit_sha="abc",
                conclusion="success",
                created_at=datetime.now(timezone.utc),
            )
        ]
        failures = build_failures_from_runs(runs)
        assert len(failures) == 0
        mock_get_files.assert_not_called()

    @patch("black_box_unlock.cicd.github_actions.get_files_changed")
    def test_handles_multiple_failures(self, mock_get_files):
        """Handles multiple failed runs."""
        mock_get_files.side_effect = [["a.py"], ["b.py"]]
        runs = [
            WorkflowRun(
                run_id=1, workflow_name="CI", commit_sha="aaa",
                conclusion="failure", created_at=datetime.now(timezone.utc),
            ),
            WorkflowRun(
                run_id=2, workflow_name="CI", commit_sha="bbb",
                conclusion="failure", created_at=datetime.now(timezone.utc),
            ),
        ]
        failures = build_failures_from_runs(runs)
        assert len(failures) == 2
```

**Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/unit/cicd/test_github_actions.py::TestBuildFailuresFromRuns -v
```

Expected: FAIL with "ImportError: cannot import name 'build_failures_from_runs'"

**Step 3: Implement build_failures_from_runs**

Add to `src/black_box_unlock/cicd/github_actions.py`:

```python
def build_failures_from_runs(runs: list[WorkflowRun]) -> list[BuildFailure]:
    """Build failure objects for failed runs with file attribution.

    Args:
        runs: List of workflow runs.

    Returns:
        List of BuildFailure objects for failed runs.
    """
    failures = []
    for run in runs:
        if not run.is_failure:
            continue
        files = get_files_changed(run.commit_sha)
        failures.append(
            BuildFailure(
                run_id=run.run_id,
                workflow_name=run.workflow_name,
                commit_sha=run.commit_sha,
                files_changed=files,
                failed_at=run.created_at,
                conclusion=run.conclusion,
            )
        )
    return failures
```

**Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/unit/cicd/test_github_actions.py -v
```

Expected: PASS (12 tests)

**Step 5: Commit**

```bash
git add src/black_box_unlock/cicd/github_actions.py tests/unit/cicd/test_github_actions.py
git commit -m "feat(cicd): add build_failures_from_runs with file attribution"
```

---

## Task 5: Aggregate File Failure Stats

**Files:**
- Modify: `src/black_box_unlock/cicd/github_actions.py`
- Test: `tests/unit/cicd/test_github_actions.py`

**Step 1: Add failing tests**

Add to `tests/unit/cicd/test_github_actions.py`:

```python
from black_box_unlock.cicd.github_actions import (
    aggregate_file_failures,
    build_failures_from_runs,
    fetch_workflow_runs,
    get_files_changed,
    parse_workflow_runs,
)


class TestAggregateFileFailures:
    """Tests for aggregating failures per file."""

    def test_counts_failures_per_file(self):
        """Counts how many failures touched each file."""
        failures = [
            BuildFailure(
                run_id=1, workflow_name="CI", commit_sha="a",
                files_changed=["src/a.py", "src/b.py"],
                failed_at=datetime.now(timezone.utc), conclusion="failure",
            ),
            BuildFailure(
                run_id=2, workflow_name="CI", commit_sha="b",
                files_changed=["src/a.py"],
                failed_at=datetime.now(timezone.utc), conclusion="failure",
            ),
        ]
        stats = aggregate_file_failures(failures)
        assert stats["src/a.py"] == 2
        assert stats["src/b.py"] == 1

    def test_empty_failures_returns_empty_dict(self):
        """Empty failures list returns empty dict."""
        stats = aggregate_file_failures([])
        assert stats == {}
```

**Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/unit/cicd/test_github_actions.py::TestAggregateFileFailures -v
```

Expected: FAIL with "ImportError: cannot import name 'aggregate_file_failures'"

**Step 3: Implement aggregate_file_failures**

Add to `src/black_box_unlock/cicd/github_actions.py`:

```python
from collections import Counter


def aggregate_file_failures(failures: list[BuildFailure]) -> dict[str, int]:
    """Aggregate failure counts per file.

    Args:
        failures: List of build failures.

    Returns:
        Dict mapping file path to failure count.
    """
    counts: Counter[str] = Counter()
    for failure in failures:
        for file in failure.files_changed:
            counts[file] += 1
    return dict(counts)
```

**Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/unit/cicd/test_github_actions.py -v
```

Expected: PASS (14 tests)

**Step 5: Commit**

```bash
git add src/black_box_unlock/cicd/github_actions.py tests/unit/cicd/test_github_actions.py
git commit -m "feat(cicd): add aggregate_file_failures for per-file stats"
```

---

## Task 6: Add build_failures Field to FileForensics

**Files:**
- Modify: `src/black_box_unlock/core/models.py`
- Test: `tests/unit/core/test_models.py`

**Step 1: Add failing test**

Add to `tests/unit/core/test_models.py`:

```python
class TestFileForensicsBuildFailures:
    """Tests for build_failures field in FileForensics."""

    def test_build_failures_defaults_to_zero(self):
        """build_failures defaults to 0."""
        forensics = FileForensics(
            path="src/main.py",
            commits=5,
            lines_changed=100,
            authors=["alice"],
            coupled_with=[],
        )
        assert forensics.build_failures == 0

    def test_build_failures_can_be_set(self):
        """build_failures can be set to a value."""
        forensics = FileForensics(
            path="src/main.py",
            commits=5,
            lines_changed=100,
            authors=["alice"],
            coupled_with=[],
            build_failures=3,
        )
        assert forensics.build_failures == 3
```

**Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/unit/core/test_models.py::TestFileForensicsBuildFailures -v
```

Expected: FAIL with "ValidationError: build_failures"

**Step 3: Add build_failures field**

Modify `src/black_box_unlock/core/models.py`, add to FileForensics class:

```python
class FileForensics(BaseModel):  # [4a.3] Combined forensics
    """Combined forensics for a single file."""

    path: str
    commits: int
    lines_changed: int
    authors: list[str]
    coupled_with: list[CouplingInfo]
    build_failures: int = 0  # NEW: CI failure count

    # ... existing computed fields ...
```

**Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/unit/core/test_models.py -v
```

Expected: PASS

**Step 5: Commit**

```bash
git add src/black_box_unlock/core/models.py tests/unit/core/test_models.py
git commit -m "feat(core): add build_failures field to FileForensics"
```

---

## Task 7: Integrate CI Data into Analysis

**Files:**
- Modify: `src/black_box_unlock/analysis.py`
- Test: `tests/unit/test_analysis.py`

**Step 1: Add failing test**

Add to `tests/unit/test_analysis.py`:

```python
class TestRunAnalysisWithCIData:
    """Tests for CI data integration in analysis."""

    @patch("black_box_unlock.analysis._fetch_ci_failures")
    @patch("black_box_unlock.analysis._fetch_gmap_data")
    def test_includes_build_failures_in_file_forensics(
        self, mock_gmap, mock_ci
    ):
        """File forensics includes build_failures from CI data."""
        mock_gmap.return_value = {
            "commits": [
                {
                    "sha": "abc",
                    "date": "2026-01-26T10:00:00",
                    "author": {"email": "test@example.com"},
                    "files": [{"path": "src/main.py", "added": 10, "deleted": 5}],
                }
            ]
        }
        mock_ci.return_value = {"src/main.py": 2}

        result = run_analysis(Path("/fake/repo"), days=30, include_ci=True)

        main_file = next(f for f in result.files if f.path == "src/main.py")
        assert main_file.build_failures == 2
```

**Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/unit/test_analysis.py::TestRunAnalysisWithCIData -v
```

Expected: FAIL

**Step 3: Implement CI integration**

Modify `src/black_box_unlock/analysis.py`:

```python
from .cicd.github_actions import (
    aggregate_file_failures,
    build_failures_from_runs,
    fetch_workflow_runs,
)


def _fetch_ci_failures() -> dict[str, int]:
    """Fetch CI failure counts per file.

    Returns:
        Dict mapping file path to failure count.
    """
    try:
        runs = fetch_workflow_runs(limit=100)
        failures = build_failures_from_runs(runs)
        return aggregate_file_failures(failures)
    except Exception:
        # CI data is optional - gracefully degrade
        return {}


def run_analysis(
    repo_path: Path,
    days: int = 30,
    min_coupling: float = 0.3,
    include_ci: bool = True,  # NEW parameter
) -> AnalysisResult:
    # ... existing code ...

    # Fetch CI data if requested
    ci_failures: dict[str, int] = {}
    if include_ci:
        ci_failures = _fetch_ci_failures()

    # Build FileForensics with CI data
    files.append(
        FileForensics(
            path=path,
            commits=churn.commits if churn else 0,
            lines_changed=churn.total_lines_changed if churn else 0,
            authors=ownership.authors if ownership else [],
            coupled_with=coupling_by_file.get(path, []),
            build_failures=ci_failures.get(path, 0),  # NEW
        )
    )
```

**Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/unit/test_analysis.py -v
```

Expected: PASS

**Step 5: Commit**

```bash
git add src/black_box_unlock/analysis.py tests/unit/test_analysis.py
git commit -m "feat: integrate CI failure data into analysis pipeline"
```

---

## Task 8: Add Build Failures Column to HTML Table

**Files:**
- Modify: `src/black_box_unlock/visualization/html.py`
- Test: `tests/unit/visualization/test_html.py`

**Step 1: Add failing test**

Add to `tests/unit/visualization/test_html.py`:

```python
def test_table_includes_build_failures_column(sample_result):
    """Table has Build Failures column header."""
    html = generate_html_report(sample_result)
    assert "<th>Build Failures</th>" in html or "Build Failures" in html
```

**Step 2: Run test to verify it fails**

```bash
uv run pytest tests/unit/visualization/test_html.py::test_table_includes_build_failures_column -v
```

Expected: FAIL

**Step 3: Add column to HTML template**

Modify the table header in `src/black_box_unlock/visualization/html.py`:

```html
<thead>
    <tr>
        <th>File</th>
        <th>Hotspot Score</th>
        <th>Commits</th>
        <th>Lines Changed</th>
        <th>Authors</th>
        <th>Build Failures</th>  <!-- NEW -->
        <th>Coupled With</th>
    </tr>
</thead>
```

And update FILE_ROW_TEMPLATE to include the value:

```python
FILE_ROW_TEMPLATE = """                <tr>
                    <td>{path}</td>
                    <td><span class="hotspot {hotspot_class}">{hotspot_score:,}</span></td>
                    <td><span class="metric {commits_class}">{commits}</span></td>
                    <td><span class="metric {lines_class}">{lines_changed:,}</span></td>
                    <td class="{risk_class}">{author_count}</td>
                    <td><span class="metric {failures_class}">{build_failures}</span></td>
                    <td class="coupling">{coupling_html}</td>
                </tr>"""
```

Update the generate_html_report function to include build_failures in format.

**Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/unit/visualization/test_html.py -v
```

Expected: PASS

**Step 5: Commit**

```bash
git add src/black_box_unlock/visualization/html.py tests/unit/visualization/test_html.py
git commit -m "feat(viz): add Build Failures column to HTML table"
```

---

## Task 9: Add --no-ci CLI Flag

**Files:**
- Modify: `src/black_box_unlock/cli.py`
- Test: `tests/unit/test_cli.py`

**Step 1: Add failing test**

Add to `tests/unit/test_cli.py`:

```python
def test_no_ci_flag_skips_ci_analysis(self, mock_run_analysis, mock_html):
    """--no-ci flag passes include_ci=False to run_analysis."""
    result = runner.invoke(app, ["analyze-repo", "--no-ci"])
    mock_run_analysis.assert_called_once()
    call_kwargs = mock_run_analysis.call_args[1]
    assert call_kwargs.get("include_ci") is False
```

**Step 2: Implement --no-ci flag**

Modify `src/black_box_unlock/cli.py`:

```python
@app.command()
def analyze_repo(
    path: Annotated[Path, typer.Argument(...)] = Path("."),
    days: Annotated[int, typer.Option("--days", "-d")] = 30,
    output: Annotated[str, typer.Option("--output", "-o")] = "html",
    no_ci: Annotated[bool, typer.Option("--no-ci")] = False,  # NEW
):
    result = run_analysis(path, days=days, include_ci=not no_ci)
    # ...
```

**Step 3: Run tests**

```bash
uv run pytest tests/unit/test_cli.py -v
```

**Step 4: Commit**

```bash
git add src/black_box_unlock/cli.py tests/unit/test_cli.py
git commit -m "feat(cli): add --no-ci flag to skip CI analysis"
```

---

## Task 10: Add requires_gh Test Marker

**Files:**
- Modify: `tests/conftest.py`

**Step 1: Add marker for gh CLI**

Add to `tests/conftest.py`:

```python
def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line(
        "markers",
        "requires_gmap: marks tests that require the gmap CLI tool",
    )
    config.addinivalue_line(
        "markers",
        "requires_gh: marks tests that require the gh CLI tool",
    )


def pytest_collection_modifyitems(config, items):
    """Skip tests that require external tools if not installed."""
    gmap_available = shutil.which("gmap") is not None
    gh_available = shutil.which("gh") is not None

    skip_gmap = pytest.mark.skip(reason="gmap CLI not installed")
    skip_gh = pytest.mark.skip(reason="gh CLI not installed")

    for item in items:
        if "requires_gmap" in item.keywords and not gmap_available:
            item.add_marker(skip_gmap)
        if "requires_gh" in item.keywords and not gh_available:
            item.add_marker(skip_gh)
```

**Step 2: Run all tests**

```bash
uv run pytest -v
```

**Step 3: Commit**

```bash
git add tests/conftest.py
git commit -m "test: add requires_gh marker for gh CLI dependent tests"
```

---

## Summary

This plan implements BBU-b7oh (Track build failures per file) with:

1. **Models** - WorkflowRun, BuildFailure
2. **Data extraction** - gh CLI wrapper, file attribution via git show
3. **Aggregation** - Per-file failure counts
4. **Integration** - Added to FileForensics model and analysis pipeline
5. **Display** - Build Failures column in HTML table
6. **CLI** - --no-ci flag for graceful opt-out
7. **Testing** - requires_gh marker for CI environments without gh

Total: 10 tasks, ~30 test cases
