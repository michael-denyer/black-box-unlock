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
                created_at=datetime.fromisoformat(item["createdAt"].replace("Z", "+00:00")),
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


def get_files_changed(commit_sha: str) -> list[str]:
    """Get list of files changed in a commit.

    Args:
        commit_sha: Git commit SHA.

    Returns:
        List of file paths changed in the commit.

    Raises:
        subprocess.CalledProcessError: If git command fails (e.g., invalid SHA).
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


def build_failures_from_runs(runs: list[WorkflowRun]) -> list[BuildFailure]:
    """Build failure objects for failed runs with file attribution.

    Args:
        runs: List of workflow runs.

    Returns:
        List of BuildFailure objects for failed runs.

    Raises:
        subprocess.CalledProcessError: If git command fails for any commit SHA.
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
