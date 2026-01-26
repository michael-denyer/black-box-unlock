"""GitHub Actions CI/CD integration via gh CLI."""

import json
import subprocess
from collections import Counter, defaultdict
from datetime import datetime

from .models import BuildFailure, FlakyStep, WorkflowRun


def parse_workflow_runs(gh_json: list[dict]) -> list[WorkflowRun]:
    """Parse gh run list JSON output into WorkflowRun objects.

    Args:
        gh_json: List of dicts from gh run list --json output.

    Returns:
        List of WorkflowRun objects.
    """
    return [
        WorkflowRun(
            run_id=item["databaseId"],
            workflow_name=item["workflowName"],
            commit_sha=item["headSha"],
            conclusion=item["conclusion"] or "unknown",
            created_at=datetime.fromisoformat(item["createdAt"].replace("Z", "+00:00")),
        )
        for item in gh_json
    ]


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
    return [line for line in result.stdout.strip().split("\n") if line.strip()]


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


def aggregate_file_failures(failures: list[BuildFailure]) -> dict[str, int]:
    """Aggregate failure counts per file.

    Args:
        failures: List of build failures.

    Returns:
        Dict mapping file path to failure count.
    """
    counts: Counter[str] = Counter()
    for failure in failures:
        counts.update(failure.files_changed)
    return dict(counts)


def fetch_all_runs(limit: int = 100) -> list[dict]:
    """Fetch workflow runs via REST API.

    Args:
        limit: Maximum number of runs to fetch.

    Returns:
        List of workflow run dicts from GitHub API.

    Raises:
        subprocess.CalledProcessError: If gh command fails.
    """
    cmd = [
        "gh",
        "api",
        f"/repos/{{owner}}/{{repo}}/actions/runs?per_page={limit}",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return json.loads(result.stdout)["workflow_runs"]


def fetch_jobs_for_run(run_id: int) -> list[dict]:
    """Fetch jobs+steps for a single run.

    Args:
        run_id: GitHub Actions run ID.

    Returns:
        List of job dicts with steps.

    Raises:
        subprocess.CalledProcessError: If gh command fails.
    """
    cmd = [
        "gh",
        "api",
        f"/repos/{{owner}}/{{repo}}/actions/runs/{run_id}/jobs",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return json.loads(result.stdout)["jobs"]


def detect_flaky_steps(runs: list[dict]) -> list[FlakyStep]:
    """Detect flaky steps by analyzing re-run patterns.

    A step is flaky if: same commit, attempt N failed, attempt N+1 passed.

    Args:
        runs: List of workflow run dicts with id, head_sha, run_attempt, conclusion.

    Returns:
        List of FlakyStep objects for steps with flakiness detected.
    """
    if not runs:
        return []

    # Group runs by (head_sha, workflow) to find re-runs
    by_commit: dict[str, list[dict]] = defaultdict(list)
    for run in runs:
        key = f"{run['head_sha']}:{run.get('workflow_name', 'unknown')}"
        by_commit[key].append(run)

    # Track step history: (job_name, step_name) -> stats
    step_stats: dict[tuple[str, str], dict] = defaultdict(
        lambda: {
            "total_runs": 0,
            "failures": 0,
            "flaky_count": 0,
            "first_seen": None,
            "last_seen": None,
        }
    )

    for _commit_key, commit_runs in by_commit.items():
        # Sort by attempt number
        commit_runs.sort(key=lambda r: r.get("run_attempt", 1))

        # Fetch job data for each run
        run_jobs: dict[int, list[dict]] = {}
        for run in commit_runs:
            run_jobs[run["id"]] = fetch_jobs_for_run(run["id"])

        for i, run in enumerate(commit_runs):
            jobs = run_jobs[run["id"]]
            for job in jobs:
                for step in job.get("steps", []):
                    key = (job["name"], step["name"])
                    stats = step_stats[key]
                    stats["total_runs"] += 1

                    # Update timestamps
                    completed = step.get("completed_at")
                    if completed:
                        ts = datetime.fromisoformat(completed.replace("Z", "+00:00"))
                        if stats["first_seen"] is None or ts < stats["first_seen"]:
                            stats["first_seen"] = ts
                        if stats["last_seen"] is None or ts > stats["last_seen"]:
                            stats["last_seen"] = ts

                    if step["conclusion"] == "failure":
                        stats["failures"] += 1
                        # Check if next attempt passed for this step
                        if i + 1 < len(commit_runs):
                            next_run = commit_runs[i + 1]
                            next_jobs = run_jobs[next_run["id"]]
                            if _step_passed_in_jobs(next_jobs, job["name"], step["name"]):
                                stats["flaky_count"] += 1

    # Convert to FlakyStep objects
    result = []
    for (job_name, step_name), stats in step_stats.items():
        if stats["flaky_count"] > 0 or (
            stats["failures"] / stats["total_runs"] > 0.1 if stats["total_runs"] > 0 else False
        ):
            result.append(
                FlakyStep(
                    job_name=job_name,
                    step_name=step_name,
                    first_seen=stats["first_seen"] or datetime.now(),
                    last_seen=stats["last_seen"] or datetime.now(),
                    total_runs=stats["total_runs"],
                    failures=stats["failures"],
                    flaky_count=stats["flaky_count"],
                )
            )
    return result


def _step_passed_in_jobs(jobs: list[dict], job_name: str, step_name: str) -> bool:
    """Check if a specific step passed in a list of jobs."""
    for job in jobs:
        if job["name"] == job_name:
            for step in job.get("steps", []):
                if step["name"] == step_name and step["conclusion"] == "success":
                    return True
    return False
