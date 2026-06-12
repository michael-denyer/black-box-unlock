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


class StepResult(BaseModel):
    """A single step execution within a job."""

    job_name: str
    step_name: str
    conclusion: str  # "success", "failure", "skipped"
    run_id: int
    attempt: int
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
    flaky_count: int  # Failed attempts that later passed on a retry

    @property
    def flaky_rate(self) -> float:
        """Calculate flakiness rate as flaky_count / total_runs."""
        return self.flaky_count / self.total_runs if self.total_runs else 0.0

    @property
    def is_active(self) -> bool:
        """Check if step ran in last 7 days."""
        from datetime import timezone

        now = datetime.now(timezone.utc)
        return (now - self.last_seen).days <= 7
