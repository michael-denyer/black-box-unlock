"""File ownership calculation from git history."""

from collections import defaultdict
from datetime import datetime
from enum import Enum
from typing import Protocol

from ..core.models import HIGH_RISK_AUTHOR_THRESHOLD, FileOwnership, is_diffuse
from .log import Commit

_GITHUB_BOT_EMAILS = frozenset({"noreply@github.com"})


def _is_bot_author(email: str) -> bool:
    """Return True for automation identities such as dependabot[bot]."""
    return "[bot]" in email or email.lower() in _GITHUB_BOT_EMAILS


class OwnershipRisk(str, Enum):
    """How a file's authorship is spread. Only ``diffuse`` is a coordination risk."""

    owned = "owned"
    shared = "shared"
    diffuse = "diffuse"
    orphaned = "orphaned"


class _OwnershipFacts(Protocol):
    @property
    def author_count(self) -> int: ...
    @property
    def main_author_share(self) -> float: ...


def ownership_risk(ownership: _OwnershipFacts) -> OwnershipRisk:
    """Classify authorship spread from author count and the main author's share.

    - diffuse: more than HIGH_RISK_AUTHOR_THRESHOLD authors and the main
      author holds less than half of the non-bot commits.
    - shared: more than the threshold, but one author holds at least half.
    - owned: the threshold or fewer authors.
    - orphaned: never returned here. It needs a last-active date that is
      judged against today, and the analysis window bounds ``last_active``:
      a file untouched for the whole window has no commits and no record.
      A consumer can compare ``last_active`` with the window end later.
    """
    if ownership.author_count <= HIGH_RISK_AUTHOR_THRESHOLD:
        return OwnershipRisk.owned
    if is_diffuse(ownership.author_count, ownership.main_author_share):
        return OwnershipRisk.diffuse
    return OwnershipRisk.shared


def parse_ownership_from_history(commits: list[Commit]) -> list[FileOwnership]:  # [3c]
    """Aggregate authors, per-author commit counts, and recency per file.

    A missing or blank author email is recorded as "unknown". Bot authors
    count toward ``commits`` but not toward authors, the main author, its
    share, or ``last_active``. The main author has the most commits; ties go
    to the author with the most recent commit, then to the lower name.
    """
    by_author: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    latest_by_author: dict[str, dict[str, datetime]] = defaultdict(dict)
    file_commits: dict[str, int] = defaultdict(int)

    for commit in commits:
        author = commit.author_email.strip() or "unknown"
        for file in commit.files:
            file_commits[file.path] += 1
            if _is_bot_author(author):
                continue
            by_author[file.path][author] += 1
            seen = latest_by_author[file.path].get(author)
            if seen is None or commit.timestamp > seen:
                latest_by_author[file.path][author] = commit.timestamp

    return [
        _build_ownership(path, total, by_author.get(path, {}), latest_by_author.get(path, {}))
        for path, total in file_commits.items()
    ]


def _build_ownership(
    path: str, total: int, counts: dict[str, int], latest: dict[str, datetime]
) -> FileOwnership:
    main_author: str | None = None
    share = 0.0
    if counts:
        main_author = min(counts, key=lambda a: (-counts[a], -latest[a].timestamp(), a))
        share = counts[main_author] / sum(counts.values())
    return FileOwnership(
        path=path,
        authors=sorted(counts),
        commits=total,
        main_author=main_author,
        main_author_share=share,
        last_active=max(latest.values()) if latest else None,
        authors_by_commits=dict(sorted(counts.items())),
    )
