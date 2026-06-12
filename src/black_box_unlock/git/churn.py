"""File churn extraction from git history."""

from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from ..core.models import FileChurn
from .log import fetch_git_history


def parse_history_entries(data: dict[str, Any]) -> list[FileChurn]:  # [3a]
    """Parse git history entries into FileChurn models.

    Aggregates commits and line changes per file across all entries.
    """
    file_stats: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"commits": 0, "lines_added": 0, "lines_deleted": 0, "timestamps": []}
    )

    for entry in data.get("entries", []):
        timestamp = datetime.fromisoformat(entry["timestamp"].replace("Z", "+00:00"))
        for file_info in entry.get("files", []):
            stats = file_stats[file_info["path"]]
            stats["commits"] += 1
            stats["lines_added"] += file_info["added_lines"]
            stats["lines_deleted"] += file_info["deleted_lines"]
            stats["timestamps"].append(timestamp)

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
