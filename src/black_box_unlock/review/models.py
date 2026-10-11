"""Typed inputs, evidence, actions, and results of a change review."""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field

from ..config import ReviewOverrides
from ..core.models import CouplingPolicy, SignalStatus
from ..git.changes import ChangedPath, ChangeProvenance, ChangeSelector
from ..path_roles import PathRoleClassification

MAX_REVIEW_COUPLINGS = 20


class ReviewParameters(BaseModel):
    """Public policies needed to interpret a review."""

    days: int = Field(default=90, ge=1)
    coupling: CouplingPolicy = Field(default_factory=CouplingPolicy)
    include_ci: bool = False
    max_actions: int = Field(default=3, ge=1, le=3)
    profile: str = Field(default="default", min_length=1)
    config_path: Literal[".bbu.toml"] | None = None

    def apply(self, overrides: ReviewOverrides) -> "ReviewParameters":
        """Return a copy with every value the overrides set, the coupling floors included."""
        values = overrides.model_dump(
            include={"days", "include_ci", "max_actions"}, exclude_none=True
        )
        coupling = self.coupling.with_overrides(
            min_ratio=overrides.min_coupling,
            min_shared_revisions=overrides.min_shared_revisions,
        )
        return self.model_copy(update={**values, "coupling": coupling})


class ChangeReviewRequest(ReviewOverrides):
    """Unresolved change selection, an optional profile name, and explicit overrides."""

    selector: ChangeSelector
    profile: str | None = Field(default=None, min_length=1)


class FileEvidence(BaseModel):
    """Historical facts retained for one selected path."""

    path: str
    role: PathRoleClassification
    commits: int = Field(ge=0)
    complexity: float = Field(ge=0)
    bugfix_commits: int = Field(ge=0)
    author_count: int = Field(ge=0)
    main_author_share: float = Field(default=0.0, ge=0.0, le=1.0)
    build_failures: int = Field(ge=0)


class ChangedFileReview(BaseModel):
    """A selected path joined with its historical facts."""

    change: ChangedPath
    evidence: FileEvidence


class CouplingEvidence(BaseModel):
    """Explainable historical relationship involving a selected path."""

    changed_path: str
    changed_path_role: PathRoleClassification
    coupled_path: str
    coupled_path_role: PathRoleClassification
    shared_revisions: int = Field(ge=1)
    changed_path_revisions: int = Field(ge=1)
    coupled_path_revisions: int = Field(ge=1)
    coupling_ratio: float = Field(ge=0.0, le=1.0)
    changed_to_coupled_rate: float = Field(ge=0.0, le=1.0)
    confidence_lower_bound: float = Field(ge=0.0, le=1.0)
    coupled_path_is_changed: bool


class TestGapEvidence(BaseModel):
    """Selected source paths with no selected test path."""

    source_paths: list[str] = Field(min_length=1)
    changed_test_paths: list[str]
    role_classifier_version: Literal[2] = 2


class FocusFileEvidence(BaseModel):
    """Defect and ownership facts that justify focused review."""

    path: str
    bugfix_commits: int = Field(ge=0)
    author_count: int = Field(ge=0)
    main_author_share: float = Field(default=0.0, ge=0.0, le=1.0)
    commits: int = Field(ge=0)
    complexity: float = Field(ge=0)


class CIFailureEvidence(BaseModel):
    """One failed run that includes at least one selected path."""

    run_id: int = Field(ge=1)
    workflow_name: str = Field(min_length=1)
    run_url: str = Field(min_length=1)
    commit_sha: str = Field(min_length=1)
    conclusion: Literal["failure", "timed_out"]
    created_at: datetime
    implicated_changed_paths: list[str] = Field(min_length=1)
    attribution: Literal["changed_in_failed_commit"] = "changed_in_failed_commit"


class CheckCoupledPathsAction(BaseModel):
    kind: Literal["check_coupled_paths"] = "check_coupled_paths"
    message: str
    evidence: list[CouplingEvidence] = Field(min_length=1, max_length=3)


class AddOrUpdateTestsAction(BaseModel):
    kind: Literal["add_or_update_tests"] = "add_or_update_tests"
    message: str
    evidence: TestGapEvidence


class FocusReviewAction(BaseModel):
    kind: Literal["focus_review"] = "focus_review"
    message: str
    evidence: list[FocusFileEvidence] = Field(min_length=1, max_length=3)


class InspectCIFailuresAction(BaseModel):
    kind: Literal["inspect_ci_failures"] = "inspect_ci_failures"
    message: str
    evidence: list[CIFailureEvidence] = Field(min_length=1, max_length=3)


ReviewAction = Annotated[
    CheckCoupledPathsAction | AddOrUpdateTestsAction | InspectCIFailuresAction | FocusReviewAction,
    Field(discriminator="kind"),
]


class ChangeReview(BaseModel):
    """A selected change plus bounded, evidence-backed actions."""

    kind: Literal["review"] = "review"
    repo: str
    generated_at: datetime
    provenance: ChangeProvenance
    parameters: ReviewParameters
    files: list[ChangedFileReview]
    couplings: list[CouplingEvidence] = Field(max_length=MAX_REVIEW_COUPLINGS)
    actions: list[ReviewAction] = Field(max_length=3)
    omitted_actions: int = Field(default=0, ge=0)
    warnings: list[str] = Field(default_factory=list)
    ci_status: SignalStatus


class NoChanges(BaseModel):
    """The selector resolved successfully but selected no paths."""

    kind: Literal["no_changes"] = "no_changes"
    repo: str
    generated_at: datetime
    provenance: ChangeProvenance
    parameters: ReviewParameters
    ci_status: SignalStatus = Field(default_factory=SignalStatus)


ChangeReviewResult = Annotated[
    ChangeReview | NoChanges,
    Field(discriminator="kind"),
]
