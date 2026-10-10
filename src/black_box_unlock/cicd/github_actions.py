"""GitHub Actions CI signal collection through one typed run snapshot."""

import json
import subprocess
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ..core.models import FailedWorkflowRun, FlakyStepSummary, SignalState, SignalStatus
from ..git.run import run_git
from .models import CIAnalysis, FlakyStep, WorkflowJob, WorkflowRun

GH_TIMEOUT_SECONDS = 60
MAX_PAGES = 10


def _gh_api_pages(endpoint: str, key: str, per_page: int, repo_path: Path) -> list[dict]:
    """Collect list items from consecutive gh api pages, bounded by MAX_PAGES.

    Stops at the first short page. Each call is bounded by GH_TIMEOUT_SECONDS
    and raises subprocess.TimeoutExpired when gh hangs.
    """
    separator = "&" if "?" in endpoint else "?"
    items: list[dict] = []
    for page in range(1, MAX_PAGES + 1):
        cmd = ["gh", "api", f"{endpoint}{separator}per_page={per_page}&page={page}"]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True,
            cwd=repo_path,
            timeout=GH_TIMEOUT_SECONDS,
        )
        batch = json.loads(result.stdout)[key]
        items.extend(batch)
        if len(batch) < per_page:
            break
    return items


def parse_workflow_runs(gh_json: list[dict]) -> list[WorkflowRun]:
    """Parse GitHub REST workflow-run objects at the external seam."""
    return [
        WorkflowRun(
            run_id=item["id"],
            workflow_name=item["name"],
            run_url=item["html_url"],
            commit_sha=item["head_sha"],
            conclusion=item["conclusion"] or "unknown",
            created_at=item["created_at"],
            run_attempt=item.get("run_attempt", 1),
        )
        for item in gh_json
    ]


def fetch_workflow_runs(
    limit: int = 100, repo_path: Path = Path("."), since: datetime | None = None
) -> list[WorkflowRun]:
    """Fetch typed workflow runs through the GitHub REST API, following pages.

    limit is the page size. since drops runs created before it, on the server
    by date and again here by exact timestamp.
    """
    endpoint = "/repos/{owner}/{repo}/actions/runs"
    if since is not None:
        endpoint += f"?created=>={since.astimezone(timezone.utc).date().isoformat()}"
    runs = parse_workflow_runs(_gh_api_pages(endpoint, "workflow_runs", limit, repo_path))
    return [run for run in runs if since is None or run.created_at >= since]


def get_files_changed(commit_sha: str, repo_path: Path = Path(".")) -> list[str]:
    """Return files changed in a commit from the analyzed local repository.

    A merge commit lists the files it brought in relative to its first parent,
    so a CI failure on a merge or merge-queue commit still implicates paths.
    """
    output = run_git(
        repo_path, ["show", "--name-only", "--format=", "-m", "--first-parent", commit_sha]
    )
    return [line for line in output.splitlines() if line.strip()]


def fetch_jobs_for_run(run_id: int, repo_path: Path = Path(".")) -> list[WorkflowJob]:
    """Fetch all jobs and retry attempts for one workflow run, following pages."""
    endpoint = f"/repos/{{owner}}/{{repo}}/actions/runs/{run_id}/jobs?filter=all"
    return [
        WorkflowJob.model_validate(item) for item in _gh_api_pages(endpoint, "jobs", 100, repo_path)
    ]


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


def flaky_steps_from_jobs(
    jobs: list[WorkflowJob], *, include_stable: bool = False
) -> list[FlakyStep]:
    """Observe each executed step of one run and flag fail-then-pass retries.

    Each returned step stands for one run in which the step executed. Only steps
    that failed and then passed on a later attempt are returned unless
    include_stable is set, which the cross-run rate needs for its denominator.
    """
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
        if flaky_count or include_stable:
            flaky.append(
                FlakyStep(
                    job_name=job_name,
                    step_name=step_name,
                    first_seen=history.first_seen or now,
                    last_seen=history.last_seen or now,
                    runs=1,
                    flaky_runs=1 if flaky_count else 0,
                    total_attempts=len(attempts),
                    failures=failures,
                    flaky_count=flaky_count,
                )
            )
    return flaky


def summarize_flaky_steps(steps: list[FlakyStep]) -> list[FlakyStepSummary]:
    """Merge per-run observations into one summary per job and step.

    Steps that never recovered in any observed run are dropped.
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
                runs=step.runs,
                flaky_runs=step.flaky_runs,
                total_attempts=step.total_attempts,
                failures=step.failures,
                flaky_count=step.flaky_count,
            )
            continue
        summary.runs += step.runs
        summary.flaky_runs += step.flaky_runs
        summary.total_attempts += step.total_attempts
        summary.failures += step.failures
        summary.flaky_count += step.flaky_count
        summary.first_seen = min(summary.first_seen, step.first_seen)
        summary.last_seen = max(summary.last_seen, step.last_seen)
    flaky = (summary for summary in summaries.values() if summary.flaky_runs)
    return sorted(flaky, key=lambda step: (step.job_name, step.step_name))


def _error_message(context: str, error: Exception) -> str:
    detail = str(error).strip() or type(error).__name__
    if isinstance(error, subprocess.CalledProcessError) and error.stderr:
        detail = f"{detail} {' '.join(error.stderr.split())}"
    return f"{context}: {detail}"


def collect_ci_signals(
    repo_path: Path = Path("."), limit: int = 100, days: int | None = None
) -> CIAnalysis:
    """Collect build failures and flaky steps from one workflow-run snapshot.

    days bounds the snapshot to runs created within that many days, matching
    the git history window. None keeps every fetched run.

    A run-specific failure produces a partial result and preserves other runs.
    Failure to acquire the run snapshot produces an explicit unavailable result.
    """
    try:
        since = datetime.now(timezone.utc) - timedelta(days=days) if days is not None else None
        runs = fetch_workflow_runs(limit=limit, repo_path=repo_path, since=since)
    except Exception as error:
        return CIAnalysis(
            status=SignalStatus(
                state=SignalState.unavailable,
                errors=[str(error).strip() or type(error).__name__],
            )
        )

    file_failures: Counter[str] = Counter()
    failed_runs: list[FailedWorkflowRun] = []
    flaky_observations: list[FlakyStep] = []
    errors: list[str] = []
    for run in runs:
        failure_conclusion = run.failure_conclusion
        if failure_conclusion is not None:
            implicated_paths: list[str] = []
            try:
                implicated_paths = get_files_changed(run.commit_sha, repo_path=repo_path)
                file_failures.update(implicated_paths)
            except Exception as error:
                errors.append(_error_message(f"files for run {run.run_id}", error))
            failed_runs.append(
                FailedWorkflowRun(
                    run_id=run.run_id,
                    workflow_name=run.workflow_name,
                    run_url=run.run_url,
                    commit_sha=run.commit_sha,
                    conclusion=failure_conclusion,
                    created_at=run.created_at,
                    implicated_paths=implicated_paths,
                )
            )
        if run.run_attempt > 1:
            try:
                jobs = fetch_jobs_for_run(run.run_id, repo_path=repo_path)
            except Exception as error:
                errors.append(_error_message(f"jobs for run {run.run_id}", error))
            else:
                flaky_observations.extend(flaky_steps_from_jobs(jobs, include_stable=True))

    state = SignalState.partial if errors else SignalState.available
    return CIAnalysis(
        status=SignalStatus(state=state, errors=errors),
        file_failures=dict(file_failures),
        failed_runs=failed_runs,
        flaky_steps=summarize_flaky_steps(flaky_observations),
    )
