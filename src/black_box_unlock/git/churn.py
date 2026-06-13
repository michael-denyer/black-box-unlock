"""File churn extraction from git history."""

from collections import defaultdict
from pathlib import Path
from typing import Any

from ..core.models import FileChurn
from .log import Commit, fetch_git_history


def parse_history_entries(commits: list[Commit]) -> list[FileChurn]:  # [3a]
    """Aggregate commits and line changes per file across the given commits."""
    file_stats: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"commits": 0, "lines_added": 0, "lines_deleted": 0, "timestamps": []}
    )

    for commit in commits:
        for file in commit.files:
            stats = file_stats[file.path]
            stats["commits"] += 1
            stats["lines_added"] += file.added_lines
            stats["lines_deleted"] += file.deleted_lines
            stats["timestamps"].append(commit.timestamp)

    return [
        FileChurn(
            path=path,
            commits=stats["commits"],
            lines_added=stats["lines_added"],
            lines_deleted=stats["lines_deleted"],
            first_commit=min(stats["timestamps"]).replace(tzinfo=None),
            last_commit=max(stats["timestamps"]).replace(tzinfo=None),
        )
        for path, stats in file_stats.items()
    ]


def extract_file_churn(repo_path: Path, since_days: int = 30) -> list[FileChurn]:  # [3a.1]
    """Extract file churn metrics from git history.

    Raises:
        NotAGitRepoError: If repo_path is not a git repository.
        GitToolNotFoundError: If git is not installed.
    """
    return parse_history_entries(fetch_git_history(repo_path, since_days))
