"""File ownership calculation from git history."""

from collections import defaultdict

from ..core.models import FileOwnership
from .log import Commit


def parse_ownership_from_history(commits: list[Commit]) -> list[FileOwnership]:  # [3c]
    """Aggregate unique authors and commit counts per file across the given commits.

    A missing or blank author email is recorded as "unknown".
    """
    file_authors: dict[str, set[str]] = defaultdict(set)
    file_commits: dict[str, int] = defaultdict(int)

    for commit in commits:
        author = commit.author_email.strip() or "unknown"
        for file in commit.files:
            file_authors[file.path].add(author)
            file_commits[file.path] += 1

    return [
        FileOwnership(path=path, authors=sorted(authors), commits=file_commits[path])
        for path, authors in file_authors.items()
    ]
