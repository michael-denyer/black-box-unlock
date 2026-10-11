"""GitHub Actions CI signal collection through one typed run snapshot."""

import json
import subprocess
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ..core.models import FailedWorkflowRun, FlakyStepStats, SignalState, SignalStatus
from ..git.run import run_git
from .models import CIAnalysis, WorkflowJob, WorkflowRun

GH_TIMEOUT_SECONDS = 60
MAX_PAGES = 10


def _gh_api_pages(
    endpoint: str, key: str, per_page: int, repo_path: Path
) -> tuple[list[dict], bool]:
    """Collect list items from consecutive gh api pages, bounded by MAX_PAGES.

    Stops at the first short page. The flag is True when the last page fetched
    was still full, meaning items beyond MAX_PAGES were left behind. Each call
    is bounded by GH_TIMEOUT_SECONDS and raises subprocess.TimeoutExpired when
    gh hangs.
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
            return items, False
    return items, True


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
) -> tuple[list[WorkflowRun], bool]:
    """Fetch typed workflow runs through the GitHub REST API, following pages.

    limit is the page size. since drops runs created before it, on the server
    by date and again here by exact timestamp. Runs sharing a created_at can
    shift between pages, so a run seen twice is kept once; a run that shifted
    out of view is lost. The flag is True when MAX_PAGES was reached with a
    full page, so older runs were not fetched.
    """
    endpoint = "/repos/{owner}/{repo}/actions/runs"
    if since is not None:
        endpoint += f"?created=>={since.astimezone(timezone.utc).date().isoformat()}"
    items, truncated = _gh_api_pages(endpoint, "workflow_runs", limit, repo_path)
    seen: set[int] = set()
    runs = []
    for run in parse_workflow_runs(items):
        if run.run_id in seen or (since is not None and run.created_at < since):
            continue
        seen.add(run.run_id)
        runs.append(run)
    return runs, truncated


def get_files_changed(commit_sha: str, repo_path: Path = Path(".")) -> list[str]:
    """Return files changed in a commit from the analyzed local repository.

    A merge commit lists the files it brought in relative to its first parent,
    so a CI failure on a merge or merge-queue commit still implicates paths.
    For a "merge main into feature" commit that is everything main brought in.
    """
    output = run_git(
        repo_path, ["show", "--name-only", "--format=", "-m", "--first-parent", commit_sha]
    )
    return [line for line in output.splitlines() if line.strip()]


def fetch_jobs_for_run(run_id: int, repo_path: Path = Path(".")) -> list[WorkflowJob]:
    """Fetch all jobs and retry attempts for one workflow run, following pages."""
    endpoint = f"/repos/{{owner}}/{{repo}}/actions/runs/{run_id}/jobs?filter=all"
    items, _ = _gh_api_pages(endpoint, "jobs", 100, repo_path)
    return [WorkflowJob.model_validate(item) for item in items]


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


def observe_steps(jobs: list[WorkflowJob]) -> list[FlakyStepStats]:
    """Record every step that executed in one run, with its retry history.

    Each record stands for one run, so ``runs`` is 1 and ``flaky_runs`` is 1
    when the step failed and then passed on a later attempt. Stable steps are
    kept because the cross-run flaky rate counts them in its denominator;
    summarize_flaky_steps drops steps that never recovered.
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

    observations: list[FlakyStepStats] = []
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
        observations.append(
            FlakyStepStats(
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
    return observations


@dataclass
class _MergedStep:
    first_seen: datetime
    last_seen: datetime
    runs: int = 0
    flaky_runs: int = 0
    total_attempts: int = 0
    failures: int = 0
    flaky_count: int = 0

    def add(self, step: FlakyStepStats) -> None:
        self.first_seen = min(self.first_seen, step.first_seen)
        self.last_seen = max(self.last_seen, step.last_seen)
        self.runs += step.runs
        self.flaky_runs += step.flaky_runs
        self.total_attempts += step.total_attempts
        self.failures += step.failures
        self.flaky_count += step.flaky_count


def summarize_flaky_steps(steps: list[FlakyStepStats]) -> list[FlakyStepStats]:
    """Merge per-run observations into one record per job and step.

    Steps that never recovered in any observed run are dropped. The merged
    counts are validated once, as a whole, when the record is built.
    """
    merged: dict[tuple[str, str], _MergedStep] = {}
    for step in steps:
        key = (step.job_name, step.step_name)
        merged.setdefault(key, _MergedStep(step.first_seen, step.last_seen)).add(step)
    flaky = [
        FlakyStepStats(job_name=job_name, step_name=step_name, **asdict(total))
        for (job_name, step_name), total in merged.items()
        if total.flaky_runs
    ]
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
        runs, truncated = fetch_workflow_runs(limit=limit, repo_path=repo_path, since=since)
    except Exception as error:
        return CIAnalysis(
            status=SignalStatus(
                state=SignalState.unavailable,
                errors=[str(error).strip() or type(error).__name__],
            )
        )

    file_failures: Counter[str] = Counter()
    failed_runs: list[FailedWorkflowRun] = []
    flaky_observations: list[FlakyStepStats] = []
    errors: list[str] = []
    if truncated:
        errors.append(f"run list truncated at {MAX_PAGES * limit} runs; older runs not examined")
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
                flaky_observations.extend(observe_steps(jobs))

    state = SignalState.partial if errors else SignalState.available
    return CIAnalysis(
        status=SignalStatus(state=state, errors=errors),
        file_failures=dict(file_failures),
        failed_runs=failed_runs,
        flaky_steps=summarize_flaky_steps(flaky_observations),
    )
