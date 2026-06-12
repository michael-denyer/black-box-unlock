"""Native git history extraction via git log --numstat."""

import subprocess
from pathlib import Path
from typing import Any

from ..core.exceptions import GitToolNotFoundError, NotAGitRepoError

# \x01 marks the start of a commit record so we never collide with file content.
_COMMIT_MARKER = "\x01"
_PRETTY_FORMAT = f"{_COMMIT_MARKER}%aI%x09%ae%x09%s"


def fetch_git_history(repo_path: Path, days: int) -> dict[str, Any]:
    """Fetch commit history with per-file line stats.

    Returns:
        Dict of shape {"entries": [{"timestamp", "author_email", "message",
        "files": [{"path", "added_lines", "deleted_lines"}]}]} — the contract
        consumed by the churn/ownership/coupling parsers.

    Raises:
        NotAGitRepoError: If repo_path is not a git repository.
        GitToolNotFoundError: If the git binary is not installed.
    """
    if not (repo_path / ".git").exists():
        raise NotAGitRepoError(f"Not a git repository: {repo_path}")

    cmd = [
        "git",
        "-C",
        str(repo_path),
        "log",
        f"--since={days} days ago",
        "--numstat",
        "--no-renames",
        f"--pretty=format:{_PRETTY_FORMAT}",
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    except FileNotFoundError as e:
        raise GitToolNotFoundError("git not found on PATH") from e
    return _parse_log_output(result.stdout)


def _parse_log_output(output: str) -> dict[str, Any]:
    """Parse git log --numstat output into the entries dict."""
    entries: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None

    for line in output.splitlines():
        if line.startswith(_COMMIT_MARKER):
            timestamp, author_email, message = line[1:].split("\t", 2)
            current = {
                "timestamp": timestamp,
                "author_email": author_email,
                "message": message,
                "files": [],
            }
            entries.append(current)
        elif line.strip() and current is not None:
            added, deleted, path = line.split("\t", 2)
            if added == "-" or deleted == "-":
                continue  # binary file
            current["files"].append(
                {"path": path, "added_lines": int(added), "deleted_lines": int(deleted)}
            )

    return {"entries": entries}
