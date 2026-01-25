"""File churn extraction from git history."""

import json
import shutil
import subprocess
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from ..core.exceptions import NotAGitRepoError
from ..core.models import FileChurn


def parse_gmap_output(data: dict[str, Any]) -> list[FileChurn]:
    """Parse gmap JSON output into FileChurn models.

    Aggregates commits and line changes per file across all entries.

    Args:
        data: Parsed JSON from gmap export --json

    Returns:
        List of FileChurn models, one per unique file path.
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


def extract_file_churn(repo_path: Path, since_days: int = 30) -> list[FileChurn]:
    """Extract file churn metrics from git history.

    Uses gmap for performance if available.

    Args:
        repo_path: Path to git repository.
        since_days: Number of days of history to analyze.

    Returns:
        List of FileChurn models for each file with commits in the period.

    Raises:
        NotAGitRepoError: If repo_path is not a git repository.
    """
    if not (repo_path / ".git").exists():
        raise NotAGitRepoError(f"Not a git repository: {repo_path}")

    gmap_path = shutil.which("gmap") or str(Path.home() / ".cargo" / "bin" / "gmap")

    cmd = [
        gmap_path,
        "--repo",
        str(repo_path),
        "--since",
        f"{since_days} days ago",
        "export",
        "--json",
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    data = json.loads(result.stdout)

    return parse_gmap_output(data)
