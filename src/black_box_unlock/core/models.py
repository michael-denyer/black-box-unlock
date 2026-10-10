"""Core data models for forensic analysis."""

from datetime import datetime, timezone
from enum import Enum
from math import sqrt
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    computed_field,
    field_validator,
    model_validator,
)

from ..path_roles import PathRole, classify_path_role

HIGH_RISK_AUTHOR_THRESHOLD = 3
"""Files with more than this many authors are considered coordination risks."""


class CouplingPolicy(BaseModel):
    """The one definition of which history counts as temporal-coupling evidence.

    ``max_changeset_size`` also marks bulk commits, which every history signal
    (churn, ownership, defects, coupling) excludes.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    min_ratio: float = Field(default=0.3, ge=0.0, le=1.0)
    min_shared_revisions: int = Field(default=2, ge=1)
    max_changeset_size: int = Field(default=50, ge=2)
    require_live_partner: bool = True


def _validate_non_empty_path(v: str) -> str:
    """Validate that path is not empty or whitespace."""
    if not v.strip():
        raise ValueError("path must not be empty")
    return v


def _validate_non_negative_int(v: int, field_name: str) -> int:
    """Validate that an integer field is non-negative."""
    if v < 0:
        raise ValueError(f"{field_name} must be non-negative")
    return v


def tornhill_ratio(shared: int, count_a: int, count_b: int) -> float:
    """Co-change coupling ratio (Tornhill): shared / min(count_a, count_b), 0 if either is 0."""
    lo = min(count_a, count_b)
    return shared / lo if lo else 0.0


def wilson_lower_bound(successes: int, trials: int, z: float = 1.96) -> float:
    """Lower bound of a Wilson score interval for a binomial proportion.

    Coupling uses the smaller file-revision count as the number of trials.
    The explicit 95% bound prevents perfect ratios from tiny samples from
    outranking repeated evidence.
    """
    if trials < 0 or successes < 0 or successes > trials:
        raise ValueError("Wilson counts must satisfy 0 <= successes <= trials")
    if trials == 0:
        return 0.0
    proportion = successes / trials
    z_squared = z * z
    denominator = 1 + z_squared / trials
    centre = proportion + z_squared / (2 * trials)
    margin = z * sqrt((proportion * (1 - proportion) + z_squared / (4 * trials)) / trials)
    return max(0.0, (centre - margin) / denominator)


class FileChurn(BaseModel):  # [4a] Churn metrics per file
    """Churn metrics for a single file."""

    path: str
    commits: int
    lines_added: int
    lines_deleted: int
    first_commit: datetime
    last_commit: datetime

    @property
    def total_lines_changed(self) -> int:
        return self.lines_added + self.lines_deleted

    @field_validator("path")
    @classmethod
    def path_must_not_be_empty(cls, v: str) -> str:
        return _validate_non_empty_path(v)

    @field_validator("commits")
    @classmethod
    def commits_must_be_non_negative(cls, v: int) -> int:
        return _validate_non_negative_int(v, "commits")


class TemporalCoupling(BaseModel):  # [4a.1] File pair co-change
    """Two files that change together frequently.

    ``coupling_ratio`` is Tornhill's symmetric co_change_count / min(commits_a,
    commits_b). The directional rates divide by one side's revisions:
    ``rate_a_to_b`` is the share of file_a's revisions that also touched file_b,
    which is what "edit file_a, check file_b" needs.
    """

    file_a: str
    file_b: str
    co_change_count: int = Field(ge=0)
    commits_a: int = Field(ge=0)
    commits_b: int = Field(ge=0)

    @model_validator(mode="after")
    def co_changes_fit_revision_counts(self) -> "TemporalCoupling":
        if self.co_change_count > min(self.commits_a, self.commits_b):
            raise ValueError("co-change count exceeds the smaller file revision count")
        return self

    @computed_field
    @property
    def coupling_ratio(self) -> float:
        """Ratio of co-changes to minimum commit count (Tornhill's formula)."""
        return tornhill_ratio(self.co_change_count, self.commits_a, self.commits_b)

    @computed_field
    @property
    def rate_a_to_b(self) -> float:
        """Share of file_a's revisions that also changed file_b."""
        return self.co_change_count / self.commits_a if self.commits_a else 0.0

    @computed_field
    @property
    def rate_b_to_a(self) -> float:
        """Share of file_b's revisions that also changed file_a."""
        return self.co_change_count / self.commits_b if self.commits_b else 0.0

    @computed_field
    @property
    def confidence_lower_bound(self) -> float:
        """95% Wilson lower bound for the symmetric coupling ratio."""
        return wilson_lower_bound(
            self.co_change_count,
            min(self.commits_a, self.commits_b),
        )


class FileOwnership(BaseModel):  # [4a.2] Authors per file
    """Ownership metrics for a single file.

    Files with many authors (>3) are coordination risks that often correlate
    with higher defect rates due to diffuse ownership.
    """

    path: str
    authors: list[str]
    commits: int

    @property
    def author_count(self) -> int:
        """Number of unique authors."""
        return len(self.authors)

    @property
    def is_high_risk(self) -> bool:
        """Files with >3 authors are coordination risks."""
        return self.author_count > HIGH_RISK_AUTHOR_THRESHOLD

    @field_validator("path")
    @classmethod
    def path_must_not_be_empty(cls, v: str) -> str:
        return _validate_non_empty_path(v)

    @field_validator("commits")
    @classmethod
    def commits_must_be_non_negative(cls, v: int) -> int:
        return _validate_non_negative_int(v, "commits")


class CouplingInfo(BaseModel):
    """Coupling relationship for display."""

    file: str
    ratio: float = Field(ge=0.0, le=1.0)
    shared_revisions: int = Field(default=0, ge=0)
    file_revisions: int = Field(default=0, ge=0)
    coupled_file_revisions: int = Field(default=0, ge=0)
    confidence_lower_bound: float = Field(default=0.0, ge=0.0, le=1.0)

    @computed_field
    @property
    def rate_to_partner(self) -> float:
        """Share of this file's revisions that also changed the partner file."""
        return self.shared_revisions / self.file_revisions if self.file_revisions else 0.0


def coupling_info_for(coupling: TemporalCoupling, file_path: str) -> CouplingInfo:
    """Orient one raw pair as display evidence for ``file_path``."""
    if file_path == coupling.file_a:
        partner = coupling.file_b
        file_revisions = coupling.commits_a
        partner_revisions = coupling.commits_b
    elif file_path == coupling.file_b:
        partner = coupling.file_a
        file_revisions = coupling.commits_b
        partner_revisions = coupling.commits_a
    else:
        raise ValueError(f"{file_path} is not part of the coupling pair")
    return CouplingInfo(
        file=partner,
        ratio=coupling.coupling_ratio,
        shared_revisions=coupling.co_change_count,
        file_revisions=file_revisions,
        coupled_file_revisions=partner_revisions,
        confidence_lower_bound=wilson_lower_bound(coupling.co_change_count, file_revisions),
    )


def coupling_info_sort_key(info: CouplingInfo) -> tuple[float, int, float, str]:
    """Stable strongest-evidence-first ordering for display projections."""
    return (
        -info.confidence_lower_bound,
        -info.shared_revisions,
        -info.ratio,
        info.file,
    )


class FunctionChurn(BaseModel):
    """Per-function churn within one file (Tornhill's X-Ray)."""

    name: str
    start_line: int = 0  # 0 = boundaries unknown (header-only attribution)
    end_line: int = 0
    revisions: int
    lines_added: int
    lines_deleted: int
    complexity: float | None = 0.0  # None = could not be measured (see reason)
    score_unavailable_reason: str | None = None

    @computed_field
    @property
    def hotspot_score(self) -> float | None:
        """Function hotspot score = revisions x complexity (file formula, function scale).

        None when complexity could not be measured, never a misleading 0.
        """
        if self.complexity is None:
            return None
        return self.revisions * self.complexity


class FunctionCoupling(BaseModel):
    """Two functions in the same file that change together (X-Ray internal coupling)."""

    function_a: str
    function_b: str
    shared_revisions: int
    revisions_a: int
    revisions_b: int

    @computed_field
    @property
    def coupling_ratio(self) -> float:
        """Ratio of shared revisions to the less-changed function (Tornhill's formula)."""
        return tornhill_ratio(self.shared_revisions, self.revisions_a, self.revisions_b)


class FileXRay(BaseModel):
    """X-Ray result for one file."""

    path: str
    days: int
    revisions_analyzed: int
    revision_cap_hit: bool
    functions: list[FunctionChurn]
    coupling: list[FunctionCoupling] = Field(default_factory=list)
    skipped: str | None = None
    """Why no X-Ray was attempted (e.g. "unsupported language"); None when it ran."""


class FileForensics(BaseModel):  # [4a.3] Combined forensics
    """Combined forensics for a single file."""

    path: str
    path_role: PathRole = Field(
        default_factory=lambda data: classify_path_role(data.get("path", "")).role
    )
    """Role of the path. Defaults to the built-in classification; analysis passes
    the role resolved with the project's ``.bbu.toml`` rules."""
    commits: int
    lines_changed: int
    complexity: float = 0.0
    authors: list[str]
    coupled_with: list[CouplingInfo]
    build_failures: int = 0
    bugfix_commits: int = 0
    functions: list[FunctionChurn] = Field(default_factory=list)
    xray_skipped: str | None = None
    """Reason X-Ray was not attempted (e.g. "unsupported language"); None otherwise."""
    xray_failed: bool = False
    """True when an X-Ray attempt on this file raised; lets consumers tell a crash
    from a file that genuinely has no attributable functions (both leave functions empty)."""

    @field_validator("build_failures")
    @classmethod
    def build_failures_must_be_non_negative(cls, v: int) -> int:
        return _validate_non_negative_int(v, "build_failures")

    @field_validator("bugfix_commits")
    @classmethod
    def bugfix_commits_must_be_non_negative(cls, v: int) -> int:
        return _validate_non_negative_int(v, "bugfix_commits")

    @computed_field
    @property
    def hotspot_score(self) -> float:
        """Hotspot score = commits x complexity (Tornhill: change frequency x complexity)."""
        return self.commits * self.complexity

    @computed_field
    @property
    def author_count(self) -> int:
        """Number of unique authors."""
        return len(self.authors)

    @computed_field
    @property
    def is_high_risk(self) -> bool:
        """Files with >3 authors are coordination risks."""
        return self.author_count > HIGH_RISK_AUTHOR_THRESHOLD


class AnalysisSummary(BaseModel):
    """Summary statistics for analysis.

    ``ignored_large_changesets`` counts bulk commits excluded from every
    history signal. ``dropped_deleted_partners`` counts coupling pairs dropped
    because one side no longer exists at HEAD.
    """

    total_files: int
    high_risk_ownership: int
    coupled_pairs: int
    xrayed_files: int = 0
    ignored_large_changesets: int = 0
    dropped_deleted_partners: int = 0


class FlakyStepStats(BaseModel):
    """A job/step's flakiness counts and seen window, per-run or merged across runs.

    ``runs`` counts the workflow runs in which the step executed. ``flaky_runs``
    counts those runs where the step failed on one attempt and passed on a
    later attempt of the same run. ``flaky_rate`` is ``flaky_runs / runs``.
    Runs where the step never executed are not in the denominator, and retry
    attempts inside one run do not inflate it. ``total_attempts``, ``failures``
    and ``flaky_count`` stay attempt-level counts for display.
    """

    job_name: str
    step_name: str
    first_seen: datetime
    last_seen: datetime
    runs: int
    flaky_runs: int
    total_attempts: int
    failures: int
    flaky_count: int

    @model_validator(mode="after")
    def _counts_consistent(self) -> "FlakyStepStats":
        """Reject impossible counts: can't recover more often than you fail, or fail
        more often than you run. Keeps flaky_rate in [0, 1] for every construction."""
        if not 0 <= self.flaky_runs <= self.runs:
            raise ValueError(
                f"flaky-step runs must satisfy 0 <= flaky_runs <= runs; "
                f"got flaky_runs={self.flaky_runs}, runs={self.runs}"
            )
        if not 0 <= self.flaky_count <= self.failures <= self.total_attempts:
            raise ValueError(
                "flaky-step counts must satisfy 0 <= flaky_count <= failures <= "
                f"total_attempts; got flaky_count={self.flaky_count}, "
                f"failures={self.failures}, total_attempts={self.total_attempts}"
            )
        return self

    @computed_field
    @property
    def flaky_rate(self) -> float:
        """flaky_runs / runs, over runs in which the step executed."""
        return self.flaky_runs / self.runs if self.runs else 0.0

    @computed_field
    @property
    def is_active(self) -> bool:
        """True if the step ran within the last 7 days."""
        return (datetime.now(timezone.utc) - self.last_seen).days <= 7


class FlakyStepSummary(FlakyStepStats):
    """Flaky-step counts merged across runs, included in AnalysisResult."""


class SignalState(str, Enum):
    """Availability of an optional analysis signal."""

    available = "available"
    partial = "partial"
    unavailable = "unavailable"
    disabled = "disabled"


class SignalStatus(BaseModel):
    """Availability and diagnostics for an optional signal."""

    state: SignalState = SignalState.disabled
    errors: list[str] = Field(default_factory=list)


class FailedWorkflowRun(BaseModel):
    """One failed workflow run and the commit paths it implicates."""

    run_id: int = Field(ge=1)
    workflow_name: str = Field(min_length=1)
    run_url: str = Field(min_length=1)
    commit_sha: str = Field(min_length=1)
    conclusion: Literal["failure", "timed_out"]
    created_at: datetime
    implicated_paths: list[str] = Field(default_factory=list)
    attribution: Literal["changed_in_failed_commit"] = "changed_in_failed_commit"


class AnalysisParameters(BaseModel):
    """Inputs and policies needed to interpret an analysis result."""

    coupling: CouplingPolicy = Field(default_factory=CouplingPolicy)
    include_ci: bool = False
    xray_top: int = Field(default=0, ge=0)


class Provenance(BaseModel):
    """Where an analysis came from, so a reader can judge how far to trust it."""

    head_oid: str | None
    analysed_at: datetime
    days: int
    include_ci: bool
    shallow_clone: bool
    bbu_version: str
    cached: bool = False


class AnalysisResult(BaseModel):  # [4a.4] Complete analysis output
    """Complete analysis output."""

    repo: str
    analyzed_days: int
    generated_at: datetime
    files: list[FileForensics]
    couplings: list[TemporalCoupling] = Field(default_factory=list)
    summary: AnalysisSummary
    parameters: AnalysisParameters = Field(default_factory=AnalysisParameters)
    ci_status: SignalStatus = Field(default_factory=SignalStatus)
    failed_ci_runs: list[FailedWorkflowRun] = Field(default_factory=list)
    flaky_steps: list[FlakyStepSummary] = Field(default_factory=list)
    provenance: Provenance | None = None
