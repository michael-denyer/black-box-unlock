"""Core data models for forensic analysis."""

from datetime import datetime, timezone
from enum import Enum
from math import sqrt

from pydantic import BaseModel, Field, computed_field, field_validator, model_validator

HIGH_RISK_AUTHOR_THRESHOLD = 3
"""Files with more than this many authors are considered coordination risks."""

DEFAULT_MAX_COUPLED_FILES_PER_COMMIT = 50
"""Bulk changesets above this size do not contribute temporal-coupling pairs."""


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

    Coupling ratio uses Tornhill's formula: co_change_count / min(commits_a, commits_b).
    A ratio >= 0.3 (30%) indicates a hidden dependency worth investigating.
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

    @property
    def coupling_ratio(self) -> float:
        """Ratio of co-changes to minimum commit count (Tornhill's formula)."""
        return tornhill_ratio(self.co_change_count, self.commits_a, self.commits_b)

    @property
    def confidence_lower_bound(self) -> float:
        """95% Wilson lower bound for the coupling ratio."""
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
        confidence_lower_bound=coupling.confidence_lower_bound,
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
    complexity: float = 0.0

    @computed_field
    @property
    def hotspot_score(self) -> float:
        """Function hotspot score = revisions x complexity (file formula, function scale)."""
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


class FileForensics(BaseModel):  # [4a.3] Combined forensics
    """Combined forensics for a single file."""

    path: str
    commits: int
    lines_changed: int
    complexity: float = 0.0
    authors: list[str]
    coupled_with: list[CouplingInfo]
    build_failures: int = 0
    bugfix_commits: int = 0
    functions: list[FunctionChurn] = Field(default_factory=list)
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
    """Summary statistics for analysis."""

    total_files: int
    high_risk_ownership: int
    coupled_pairs: int
    xrayed_files: int = 0
    ignored_large_changesets: int = 0


class FlakyStepStats(BaseModel):
    """A job/step's flakiness counts and seen window, per-run or merged across runs."""

    job_name: str
    step_name: str
    first_seen: datetime
    last_seen: datetime
    total_attempts: int
    failures: int
    flaky_count: int

    @model_validator(mode="after")
    def _counts_consistent(self) -> "FlakyStepStats":
        """Reject impossible counts: can't recover more often than you fail, or fail
        more often than you run. Keeps flaky_rate in [0, 1] for every construction."""
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
        """flaky_count / total_attempts (recoveries per attempt observation)."""
        return self.flaky_count / self.total_attempts if self.total_attempts else 0.0

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


class AnalysisParameters(BaseModel):
    """Inputs and policies needed to interpret an analysis result."""

    min_coupling: float = Field(default=0.3, ge=0.0, le=1.0)
    include_ci: bool = False
    xray_top: int = Field(default=0, ge=0)
    max_coupled_files_per_commit: int = Field(
        default=DEFAULT_MAX_COUPLED_FILES_PER_COMMIT,
        ge=2,
    )


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
    flaky_steps: list[FlakyStepSummary] = Field(default_factory=list)
