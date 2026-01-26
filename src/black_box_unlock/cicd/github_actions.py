"""GitHub Actions CI/CD integration via gh CLI."""

import json
import subprocess
from datetime import datetime

from .models import WorkflowRun


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
