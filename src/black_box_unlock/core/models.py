"""Core data models for forensic analysis."""

from datetime import datetime, timezone

from pydantic import BaseModel, computed_field, field_validator

HIGH_RISK_AUTHOR_THRESHOLD = 3
"""Files with more than this many authors are considered coordination risks."""


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
    co_change_count: int
    commits_a: int
    commits_b: int

    @property
    def coupling_ratio(self) -> float:
        """Ratio of co-changes to minimum commit count (Tornhill's formula)."""
        return tornhill_ratio(self.co_change_count, self.commits_a, self.commits_b)


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
    ratio: float


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
    coupling: list[FunctionCoupling] = []


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
    functions: list[FunctionChurn] = []

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


class FlakyStepStats(BaseModel):
    """A job/step's flakiness counts and seen window, per-run or merged across runs."""

    job_name: str
    step_name: str
    first_seen: datetime
    last_seen: datetime
    total_attempts: int
    failures: int
    flaky_count: int

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


class AnalysisResult(BaseModel):  # [4a.4] Complete analysis output
    """Complete analysis output."""

    repo: str
    analyzed_days: int
    generated_at: datetime
    files: list[FileForensics]
    summary: AnalysisSummary
    flaky_steps: list[FlakyStepSummary] = []
