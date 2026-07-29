"""GitHub Actions CI signal collection through one typed run snapshot."""

import json
import subprocess
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from ..core.models import FlakyStepSummary, SignalState, SignalStatus
from .models import CIAnalysis, FlakyStep, WorkflowJob, WorkflowRun


def parse_workflow_runs(gh_json: list[dict]) -> list[WorkflowRun]:
    """Parse GitHub REST workflow-run objects at the external seam."""
    return [
        WorkflowRun(
            run_id=item["id"],
            workflow_name=item["name"],
            commit_sha=item["head_sha"],
            conclusion=item["conclusion"] or "unknown",
            created_at=item["created_at"],
            run_attempt=item.get("run_attempt", 1),
        )
        for item in gh_json
    ]


def fetch_workflow_runs(limit: int = 100, repo_path: Path = Path(".")) -> list[WorkflowRun]:
    """Fetch one typed workflow-run snapshot through the GitHub REST API."""
    cmd = [
        "gh",
        "api",
        f"/repos/{{owner}}/{{repo}}/actions/runs?per_page={limit}",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True, cwd=repo_path)
    return parse_workflow_runs(json.loads(result.stdout)["workflow_runs"])


def get_files_changed(commit_sha: str, repo_path: Path = Path(".")) -> list[str]:
    """Return files changed in a commit from the analyzed local repository."""
    cmd = [
        "git",
        "show",
        "--name-only",
        "--format=",
        commit_sha,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True, cwd=repo_path)
    return [line for line in result.stdout.splitlines() if line.strip()]


def fetch_jobs_for_run(run_id: int, repo_path: Path = Path(".")) -> list[WorkflowJob]:
    """Fetch all jobs and retry attempts for one workflow run."""
    cmd = [
        "gh",
        "api",
        f"/repos/{{owner}}/{{repo}}/actions/runs/{run_id}/jobs?filter=all&per_page=100",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True, cwd=repo_path)
    return [WorkflowJob.model_validate(item) for item in json.loads(result.stdout)["jobs"]]


@dataclass
class _StepHistory:
    attempts: list[tuple[int, str]] = field(default_factory=list)
    first_seen: datetime | None = None
    last_seen: datetime | None = None

    def observe(self, attempt: int, conclusion: str, completed_at: datetime | None) -> None:
        self.attempts.append((attempt, conclusion))
        if completed_at is None:
            return
        if self.first_seen is None or completed_at < self.first_seen:
            self.first_seen = completed_at
        if self.last_seen is None or completed_at > self.last_seen:
            self.last_seen = completed_at


def flaky_steps_from_jobs(jobs: list[WorkflowJob]) -> list[FlakyStep]:
    """Detect steps that failed and then passed on a later run attempt."""
    histories: dict[tuple[str, str], _StepHistory] = defaultdict(_StepHistory)
    for job in jobs:
        for step in job.steps:
            if step.conclusion not in ("success", "failure"):
                continue
            histories[(job.name, step.name)].observe(
                job.run_attempt,
                step.conclusion,
                step.completed_at,
            )

    flaky: list[FlakyStep] = []
    now = datetime.now(timezone.utc)
    for (job_name, step_name), history in histories.items():
        attempts = sorted(history.attempts)
        failures = sum(1 for _, conclusion in attempts if conclusion == "failure")
        flaky_count = sum(
            1
            for index, (attempt, conclusion) in enumerate(attempts)
            if conclusion == "failure"
            and any(
                later_conclusion == "success"
                for later_attempt, later_conclusion in attempts[index + 1 :]
                if later_attempt > attempt
            )
        )
        if flaky_count:
            flaky.append(
                FlakyStep(
                    job_name=job_name,
                    step_name=step_name,
                    first_seen=history.first_seen or now,
                    last_seen=history.last_seen or now,
                    total_attempts=len(attempts),
                    failures=failures,
                    flaky_count=flaky_count,
                )
            )
    return flaky


def summarize_flaky_steps(steps: list[FlakyStep]) -> list[FlakyStepSummary]:
    """Merge per-run observations into one summary per job and step."""
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
            continue
        summary.total_attempts += step.total_attempts
        summary.failures += step.failures
        summary.flaky_count += step.flaky_count
        summary.first_seen = min(summary.first_seen, step.first_seen)
        summary.last_seen = max(summary.last_seen, step.last_seen)
    return sorted(summaries.values(), key=lambda step: (step.job_name, step.step_name))


def _error_message(context: str, error: Exception) -> str:
    detail = str(error).strip() or type(error).__name__
    return f"{context}: {detail}"


def collect_ci_signals(repo_path: Path = Path("."), limit: int = 100) -> CIAnalysis:
    """Collect build failures and flaky steps from one workflow-run snapshot.

    A run-specific failure produces a partial result and preserves other runs.
    Failure to acquire the run snapshot produces an explicit unavailable result.
    """
    try:
        runs = fetch_workflow_runs(limit=limit, repo_path=repo_path)
    except Exception as error:
        return CIAnalysis(
            status=SignalStatus(
                state=SignalState.unavailable,
                errors=[str(error).strip() or type(error).__name__],
            )
        )

    file_failures: Counter[str] = Counter()
    flaky_observations: list[FlakyStep] = []
    errors: list[str] = []
    for run in runs:
        if run.is_failure:
            try:
                file_failures.update(get_files_changed(run.commit_sha, repo_path=repo_path))
            except Exception as error:
                errors.append(_error_message(f"files for run {run.run_id}", error))
        if run.run_attempt > 1:
            try:
                jobs = fetch_jobs_for_run(run.run_id, repo_path=repo_path)
            except Exception as error:
                errors.append(_error_message(f"jobs for run {run.run_id}", error))
            else:
                flaky_observations.extend(flaky_steps_from_jobs(jobs))

    state = SignalState.partial if errors else SignalState.available
    return CIAnalysis(
        status=SignalStatus(state=state, errors=errors),
        file_failures=dict(file_failures),
        flaky_steps=summarize_flaky_steps(flaky_observations),
    )
