"""Typed GitHub Actions input and CI analysis models."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from ..core.models import FailedWorkflowRun, FlakyStepStats, FlakyStepSummary, SignalStatus


class WorkflowRun(BaseModel):
    """A GitHub Actions workflow run parsed at the external seam."""

    run_id: int = Field(ge=1)
    workflow_name: str = Field(min_length=1)
    run_url: str = Field(min_length=1)
    commit_sha: str = Field(min_length=1)
    conclusion: str
    created_at: datetime
    run_attempt: int = Field(default=1, ge=1)

    @property
    def is_failure(self) -> bool:
        """Whether the run contributes build-failure attribution."""
        return self.failure_conclusion is not None

    @property
    def failure_conclusion(self) -> Literal["failure", "timed_out"] | None:
        """Narrow a raw GitHub conclusion to the two failure variants."""
        if self.conclusion == "failure":
            return "failure"
        if self.conclusion == "timed_out":
            return "timed_out"
        return None


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
    failed_runs: list[FailedWorkflowRun] = Field(default_factory=list)
    flaky_steps: list[FlakyStepSummary] = Field(default_factory=list)
