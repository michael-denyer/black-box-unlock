"""Core data models for forensic analysis."""

from datetime import datetime

from pydantic import BaseModel, field_validator


class FileChurn(BaseModel):
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
        if not v.strip():
            raise ValueError("path must not be empty")
        return v

    @field_validator("commits")
    @classmethod
    def commits_must_be_non_negative(cls, v: int) -> int:
        if v < 0:
            raise ValueError("commits must be non-negative")
        return v


class TemporalCoupling(BaseModel):
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
        min_commits = min(self.commits_a, self.commits_b)
        if min_commits == 0:
            return 0.0
        return self.co_change_count / min_commits


class FileOwnership(BaseModel):
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
        return self.author_count > 3

    @field_validator("path")
    @classmethod
    def path_must_not_be_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("path must not be empty")
        return v

    @field_validator("commits")
    @classmethod
    def commits_must_be_non_negative(cls, v: int) -> int:
        if v < 0:
            raise ValueError("commits must be non-negative")
        return v
