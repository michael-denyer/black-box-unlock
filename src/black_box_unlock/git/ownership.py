"""File ownership calculation from git history."""

from collections import defaultdict

from ..core.models import FileOwnership
from .log import Commit

_GITHUB_BOT_EMAILS = frozenset({"noreply@github.com"})


def _is_bot_author(email: str) -> bool:
    """Return True for automation identities such as dependabot[bot]."""
    return "[bot]" in email or email.lower() in _GITHUB_BOT_EMAILS


def parse_ownership_from_history(commits: list[Commit]) -> list[FileOwnership]:  # [3c]
    """Aggregate unique authors and commit counts per file across the given commits.

    A missing or blank author email is recorded as "unknown". Bot authors
    count toward commits but not toward authors.
    """
    file_authors: dict[str, set[str]] = defaultdict(set)
    file_commits: dict[str, int] = defaultdict(int)

    for commit in commits:
        author = commit.author_email.strip() or "unknown"
        for file in commit.files:
            if not _is_bot_author(author):
                file_authors[file.path].add(author)
            file_commits[file.path] += 1

    return [
        FileOwnership(path=path, authors=sorted(file_authors[path]), commits=commits)
        for path, commits in file_commits.items()
    ]
