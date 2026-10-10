"""Native git history extraction via git log --numstat.

`fetch_git_history` is the boundary: it parses raw git output into typed
`Commit` models once, so downstream forensics never touch raw strings or
re-parse timestamps. It also follows renames, so every path it returns is the
file's name at the end of the history.
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
    """One file's line delta within a commit (line counts default 0 for callers that ignore them).

    ``path`` is the file's name at the end of the history. ``former_paths``
    lists the other names it had in this commit: the source of a rename, or
    the name an older commit recorded before a later rename.
    """

    path: str
    added_lines: int = 0
    deleted_lines: int = 0
    former_paths: list[str] = []


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

    Renames detected within the window are followed: each file is reported
    under its name at the end of the history, and older names move to
    ``CommitFile.former_paths``. Detection uses git's default similarity
    threshold (50%); bbu does not expose ``--find-renames`` tuning. A path
    reused after its file was renamed away stays a separate file.

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
            "--find-renames",
            "-z",
            f"--pretty=format:{_PRETTY_FORMATS[clock]}",
            *([rev] if rev is not None else []),
        ],
        tolerate_unborn=True,
    )
    return _parse_log_output(output)


def _parse_log_output(output: str) -> list[Commit]:
    """Parse NUL-delimited git log --numstat output, newest commit first, into Commit models.

    With -z, a commit header ends in a newline that runs straight into its
    first numstat record, and a rename record is ``added\\tdeleted\\t`` followed
    by the old and new paths as separate NUL-terminated fields.

    Walking from newest to oldest, ``current_names`` maps a name seen in older
    history to the file's final name. A rename's effect starts at the commit
    below it, so the renames a commit records apply once it is fully parsed.
    """
    commits: list[Commit] = []
    current: Commit | None = None
    current_names: dict[str, str] = {}
    pending_renames: list[tuple[str, str]] = []
    fields = iter(output.split("\0"))

    for field in fields:
        if field.startswith(_COMMIT_MARKER):
            _apply_renames(current_names, pending_renames)
            header, _, field = field[1:].partition("\n")
            timestamp, author_email, message = header.split("\t", 2)
            current = Commit(timestamp=timestamp, author_email=author_email, message=message)
            commits.append(current)
        if not field.strip() or current is None:
            continue
        added, deleted, path = field.split("\t", 2)
        previous_path = None
        if not path:
            previous_path, path = next(fields), next(fields)
            pending_renames.append((previous_path, path))
        if added == "-" or deleted == "-":
            continue  # binary file
        # Merge commits emit no numstat records and so yield files: [] by design.
        final_path = current_names.get(path, path)
        names = dict.fromkeys(name for name in (previous_path, path) if name)
        _add_file(
            current,
            CommitFile(
                path=final_path,
                added_lines=int(added),
                deleted_lines=int(deleted),
                former_paths=[name for name in names if name != final_path],
            ),
        )

    return commits


def _apply_renames(current_names: dict[str, str], renames: list[tuple[str, str]]) -> None:
    """Point each rename's old name at the file's final name; free the new name for older history."""
    targets = {old: current_names.get(new, new) for old, new in renames}
    for _, new in renames:
        current_names.pop(new, None)
    current_names.update(targets)
    renames.clear()


def _add_file(commit: Commit, file: CommitFile) -> None:
    """Append file to commit, merging it into an entry that already has the same path."""
    for index, existing in enumerate(commit.files):
        if existing.path == file.path:
            commit.files[index] = merge_commit_files(existing, file)
            return
    commit.files.append(file)


def merge_commit_files(first: CommitFile, second: CommitFile) -> CommitFile:
    """Combine two records of one file within a commit into one."""
    return first.model_copy(
        update={
            "added_lines": first.added_lines + second.added_lines,
            "deleted_lines": first.deleted_lines + second.deleted_lines,
            "former_paths": list(dict.fromkeys(first.former_paths + second.former_paths)),
        }
    )
