"""Typed GitHub Actions input and CI analysis models."""

from datetime import datetime

from pydantic import BaseModel, Field

from ..core.models import FlakyStepStats, FlakyStepSummary, SignalStatus


class WorkflowRun(BaseModel):
    """A GitHub Actions workflow run parsed at the external seam."""

    run_id: int
    workflow_name: str
    commit_sha: str
    conclusion: str
    created_at: datetime
    run_attempt: int = Field(default=1, ge=1)

    @property
    def is_failure(self) -> bool:
        """Whether the run contributes build-failure attribution."""
        return self.conclusion in ("failure", "timed_out")


class WorkflowStep(BaseModel):
    """A step from the GitHub jobs response."""

    name: str
    conclusion: str | None = None
    completed_at: datetime | None = None


class WorkflowJob(BaseModel):
    """One workflow job from one run attempt."""

    name: str
    run_attempt: int = Field(default=1, ge=1)
    steps: list[WorkflowStep] = Field(default_factory=list)


class FlakyStep(FlakyStepStats):
    """One run's flakiness observation before the cross-run merge."""


class CIAnalysis(BaseModel):
    """Complete optional CI signal result, including availability."""

    status: SignalStatus
    file_failures: dict[str, int] = Field(default_factory=dict)
    flaky_steps: list[FlakyStepSummary] = Field(default_factory=list)
