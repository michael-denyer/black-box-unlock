"""Native git history extraction via git log --numstat.

`fetch_git_history` is the boundary: it parses raw git output into typed
`Commit` models once, so downstream forensics never touch raw strings or
re-parse timestamps.
"""

from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from .run import run_git

Clock = Literal["author", "committer"]

# \x01 marks the start of a commit record so we never collide with file content.
_COMMIT_MARKER = "\x01"
# %x09 is a git-side tab — the field separator _parse_log_output splits on.
# %aE applies .mailmap so one person with several emails counts once.
_PRETTY_FORMATS: dict[Clock, str] = {
    "author": f"{_COMMIT_MARKER}%aI%x09%aE%x09%s",
    "committer": f"{_COMMIT_MARKER}%cI%x09%aE%x09%s",
}


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

    def is_bulk(self, max_changeset_size: int) -> bool:
        """True when the commit touches more distinct paths than max_changeset_size."""
        return len({file.path for file in self.files}) > max_changeset_size


def exclude_bulk(commits: list[Commit], max_changeset_size: int) -> tuple[list[Commit], int]:
    """Drop bulk commits (migrations, vendoring, reformatting) and count them."""
    kept = [commit for commit in commits if not commit.is_bulk(max_changeset_size)]
    return kept, len(commits) - len(kept)


def fetch_git_history(
    repo_path: Path, days: int, rev: str | None = None, *, clock: Clock = "author"
) -> list[Commit]:
    """Fetch commit history with per-file line stats as typed Commit models.

    History ends at rev when given, otherwise at HEAD. A range such as
    `a..b` is accepted as rev.

    `--since` always filters on committer date. `clock` picks which date each
    Commit's timestamp records: author (the default, what the forensics show)
    or committer (what orders history; validation uses it so one clock both
    filters the window and splits it).

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
            f"--pretty=format:{_PRETTY_FORMATS[clock]}",
            *([rev] if rev is not None else []),
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
