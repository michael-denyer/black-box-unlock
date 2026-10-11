"""File churn extraction from git history."""

from collections import defaultdict

from ..core.models import FileChurn
from .log import Commit


def parse_history_entries(commits: list[Commit]) -> list[FileChurn]:  # [3a]
    """Aggregate commits and line changes per file across the given commits."""
    file_stats: dict[str, dict[str, int]] = defaultdict(
        lambda: {"commits": 0, "lines_added": 0, "lines_deleted": 0}
    )

    for commit in commits:
        for file in commit.files:
            stats = file_stats[file.path]
            stats["commits"] += 1
            stats["lines_added"] += file.added_lines
            stats["lines_deleted"] += file.deleted_lines

    return [FileChurn(path=path, **stats) for path, stats in file_stats.items()]
