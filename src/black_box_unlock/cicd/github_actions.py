"""GitHub Actions CI/CD integration via gh CLI."""

import json
import subprocess
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from ..core.models import FlakyStepSummary
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


def fetch_workflow_runs(limit: int = 100, repo_path: Path = Path(".")) -> list[WorkflowRun]:
    """Fetch recent workflow runs via gh CLI.

    Args:
        limit: Maximum number of runs to fetch.
        repo_path: Path to the git repository (sets cwd for gh subprocess).

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
    result = subprocess.run(cmd, capture_output=True, text=True, check=True, cwd=repo_path)
    gh_json = json.loads(result.stdout)
    return parse_workflow_runs(gh_json)


def get_files_changed(commit_sha: str, repo_path: Path = Path(".")) -> list[str]:
    """Get list of files changed in a commit.

    Args:
        commit_sha: Git commit SHA.
        repo_path: Path to the git repository (sets cwd for git subprocess).

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
    result = subprocess.run(cmd, capture_output=True, text=True, check=True, cwd=repo_path)
    return [line for line in result.stdout.strip().split("\n") if line.strip()]


def build_failures_from_runs(
    runs: list[WorkflowRun], repo_path: Path = Path(".")
) -> list[BuildFailure]:
    """Build failure objects for failed runs with file attribution.

    Args:
        runs: List of workflow runs.
        repo_path: Path to the git repository (sets cwd for git subprocess).

    Returns:
        List of BuildFailure objects for failed runs.

    Raises:
        subprocess.CalledProcessError: If git command fails for any commit SHA.
    """
    failures = []
    for run in runs:
        if not run.is_failure:
            continue
        files = get_files_changed(run.commit_sha, repo_path=repo_path)
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


def fetch_all_runs(limit: int = 100, repo_path: Path = Path(".")) -> list[dict]:
    """Fetch workflow runs via REST API.

    Args:
        limit: Maximum number of runs to fetch.
        repo_path: Path to the git repository (sets cwd for gh subprocess).

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
    result = subprocess.run(cmd, capture_output=True, text=True, check=True, cwd=repo_path)
    return json.loads(result.stdout)["workflow_runs"]


def fetch_jobs_for_run(run_id: int, repo_path: Path = Path(".")) -> list[dict]:
    """Fetch jobs+steps for a run, across ALL retry attempts.

    Args:
        run_id: GitHub Actions run ID.
        repo_path: Repository whose gh context to use (sets cwd).

    Returns:
        List of job dicts with steps; each job carries its run_attempt.

    Raises:
        subprocess.CalledProcessError: If gh command fails.
    """
    cmd = [
        "gh",
        "api",
        f"/repos/{{owner}}/{{repo}}/actions/runs/{run_id}/jobs?filter=all&per_page=100",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True, cwd=repo_path)
    return json.loads(result.stdout)["jobs"]


def flaky_steps_from_jobs(jobs: list[dict]) -> list[FlakyStep]:
    """Detect flaky steps within one run's jobs across retry attempts.

    A step is flaky when it failed in an earlier attempt and succeeded
    in a later one. Jobs must carry run_attempt (use filter=all).

    Args:
        jobs: Job dicts from /actions/runs/{id}/jobs?filter=all, each
            carrying run_attempt and a list of steps.

    Returns:
        List of FlakyStep objects, one per job/step combination that
        recovered on a strictly later attempt.
    """
    step_stats: dict[tuple[str, str], dict] = defaultdict(
        lambda: {
            "attempts": [],  # (run_attempt, conclusion)
            "first_seen": None,
            "last_seen": None,
        }
    )

    for job in jobs:
        attempt = job.get("run_attempt", 1)
        for step in job.get("steps", []):
            conclusion = step.get("conclusion")
            if conclusion not in ("success", "failure"):
                continue
            stats = step_stats[(job["name"], step["name"])]
            stats["attempts"].append((attempt, conclusion))

            completed = step.get("completed_at")
            if completed:
                ts = datetime.fromisoformat(completed.replace("Z", "+00:00"))
                if stats["first_seen"] is None or ts < stats["first_seen"]:
                    stats["first_seen"] = ts
                if stats["last_seen"] is None or ts > stats["last_seen"]:
                    stats["last_seen"] = ts

    flaky: list[FlakyStep] = []
    now = datetime.now(timezone.utc)
    for (job_name, step_name), stats in step_stats.items():
        attempts = sorted(stats["attempts"])
        failures = sum(1 for _, c in attempts if c == "failure")
        flaky_count = sum(
            1
            for i, (attempt_i, conclusion) in enumerate(attempts)
            if conclusion == "failure"
            and any(c == "success" for a, c in attempts[i + 1 :] if a > attempt_i)
        )
        if flaky_count == 0:
            continue
        flaky.append(
            FlakyStep(
                job_name=job_name,
                step_name=step_name,
                first_seen=stats["first_seen"] or now,
                last_seen=stats["last_seen"] or now,
                total_attempts=len(attempts),
                failures=failures,
                flaky_count=flaky_count,
            )
        )
    return flaky


def summarize_flaky_steps(steps: list[FlakyStep]) -> list[FlakyStepSummary]:
    """Merge per-run flaky observations into one summary per (job, step).

    Counts (attempts, failures, recoveries) sum across observations; the seen
    window spans the earliest first_seen to the latest last_seen.
    """
    summaries: dict[tuple[str, str], FlakyStepSummary] = {}
    for step in steps:
        key = (step.job_name, step.step_name)
        summary = summaries.get(key)
        if summary is None:
            summaries[key] = FlakyStepSummary(
                job_name=step.job_name,
                step_name=step.step_name,
                first_seen=step.first_seen,
                last_seen=step.last_seen,
                total_attempts=step.total_attempts,
                failures=step.failures,
                flaky_count=step.flaky_count,
            )
        else:
            summary.total_attempts += step.total_attempts
            summary.failures += step.failures
            summary.flaky_count += step.flaky_count
            summary.first_seen = min(summary.first_seen, step.first_seen)
            summary.last_seen = max(summary.last_seen, step.last_seen)
    return list(summaries.values())


def detect_flaky_steps(repo_path: Path = Path("."), limit: int = 100) -> list[FlakyStep]:
    """Detect flaky CI steps by inspecting re-run workflow runs.

    Only runs with run_attempt > 1 are inspected (one jobs call each),
    so the API cost is 1 + number-of-reruns, not 1 + number-of-runs.

    Args:
        repo_path: Repository whose gh context to use (sets cwd).
        limit: Maximum number of workflow runs to scan.

    Returns:
        List of FlakyStep objects across all inspected re-run runs.
    """
    runs = fetch_all_runs(limit=limit, repo_path=repo_path)
    flaky: list[FlakyStep] = []
    for run in runs:
        if run.get("run_attempt", 1) <= 1:
            continue
        jobs = fetch_jobs_for_run(run["id"], repo_path=repo_path)
        flaky.extend(flaky_steps_from_jobs(jobs))
    return flaky
