"""Native git history extraction via git log --numstat."""

import subprocess
from pathlib import Path
from typing import Any

from ..core.exceptions import GitToolNotFoundError, NotAGitRepoError

# \x01 marks the start of a commit record so we never collide with file content.
_COMMIT_MARKER = "\x01"
# %x09 is a git-side tab — the field separator _parse_log_output splits on.
_PRETTY_FORMAT = f"{_COMMIT_MARKER}%aI%x09%ae%x09%s"


def fetch_git_history(repo_path: Path, days: int) -> dict[str, Any]:
    """Fetch commit history with per-file line stats.

    Returns:
        Dict of shape {"entries": [{"timestamp", "author_email", "message",
        "files": [{"path", "added_lines", "deleted_lines"}]}]} — the contract
        consumed by the churn/ownership/coupling parsers. An empty repo
        (unborn HEAD) returns {"entries": []}.

    Raises:
        NotAGitRepoError: If repo_path is not a git repository.
        GitToolNotFoundError: If the git binary is not installed.
    """
    if not (repo_path / ".git").exists():
        raise NotAGitRepoError(f"Not a git repository: {repo_path}")

    cmd = [
        "git",
        "-c",
        "core.quotePath=false",
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
    except subprocess.CalledProcessError as e:
        if e.returncode == 128 and (
            "does not have any commits" in e.stderr or "bad default revision" in e.stderr
        ):
            return {"entries": []}  # freshly initialized repo: no history yet
        raise
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
            # Merge commits emit no numstat lines and so yield files: [] by design.
            current["files"].append(
                {"path": path, "added_lines": int(added), "deleted_lines": int(deleted)}
            )

    return {"entries": entries}
