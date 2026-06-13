"""Native git history extraction via git log --numstat.

`fetch_git_history` is the boundary: it parses raw git output into typed
`Commit` models once, so downstream forensics never touch raw strings or
re-parse timestamps.
"""

from datetime import datetime
from pathlib import Path

from pydantic import BaseModel

from .run import run_git

# \x01 marks the start of a commit record so we never collide with file content.
_COMMIT_MARKER = "\x01"
# %x09 is a git-side tab — the field separator _parse_log_output splits on.
_PRETTY_FORMAT = f"{_COMMIT_MARKER}%aI%x09%ae%x09%s"


class CommitFile(BaseModel):
    """One file's line delta within a commit (line counts default 0 for callers that ignore them)."""

    path: str
    added_lines: int = 0
    deleted_lines: int = 0


class Commit(BaseModel):
    """One commit's history record. The timestamp is parsed once, here at the boundary."""

    timestamp: datetime
    author_email: str = ""
    message: str = ""
    files: list[CommitFile] = []


def fetch_git_history(repo_path: Path, days: int) -> list[Commit]:
    """Fetch commit history with per-file line stats as typed Commit models.

    An empty repo (unborn HEAD) returns an empty list.

    Raises:
        NotAGitRepoError: If repo_path is not a git repository.
        GitToolNotFoundError: If the git binary is not installed.
    """
    output = run_git(
        repo_path,
        [
            "log",
            f"--since={days} days ago",
            "--numstat",
            "--no-renames",
            f"--pretty=format:{_PRETTY_FORMAT}",
        ],
        tolerate_unborn=True,
    )
    return _parse_log_output(output)


def _parse_log_output(output: str) -> list[Commit]:
    """Parse git log --numstat output into Commit models."""
    commits: list[Commit] = []
    current: Commit | None = None

    for line in output.splitlines():
        if line.startswith(_COMMIT_MARKER):
            timestamp, author_email, message = line[1:].split("\t", 2)
            current = Commit(timestamp=timestamp, author_email=author_email, message=message)
            commits.append(current)
        elif line.strip() and current is not None:
            added, deleted, path = line.split("\t", 2)
            if added == "-" or deleted == "-":
                continue  # binary file
            # Merge commits emit no numstat lines and so yield files: [] by design.
            current.files.append(
                CommitFile(path=path, added_lines=int(added), deleted_lines=int(deleted))
            )

    return commits
