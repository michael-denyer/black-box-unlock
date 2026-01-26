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
