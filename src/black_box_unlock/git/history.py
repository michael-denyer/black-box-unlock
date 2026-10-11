"""One repository's history over a window, with the path identity every signal joins on."""

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from ..core.models import CouplingPolicy
from .log import Commit, exclude_bulk, fetch_git_history
from .run import head_paths


@dataclass(frozen=True)
class HistoryWindow:
    """Non-bulk commits in a window plus the facts about path identity the signals share.

    ``renamed_from`` maps each current path to the older names it had in the
    window. ``aliases`` is the reverse map, every older name to its current
    path, for evidence recorded outside git such as CI runs. ``live_paths`` is
    the set of paths a coupling partner must be in, or None when the policy
    keeps partners deleted at the end of the window.
    """

    commits: list[Commit]
    ignored_bulk_commits: int
    live_paths: frozenset[str] | None
    renamed_from: dict[str, list[str]]
    aliases: dict[str, str]


def load_history_window(
    repo_path: Path,
    days: int,
    policy: CouplingPolicy,
    *,
    rev: str | None = None,
    aliases: dict[str, str] | None = None,
    ensure_paths: frozenset[str] = frozenset(),
) -> HistoryWindow:
    """Fetch the window ending at rev (HEAD when None) and drop bulk commits.

    ``aliases`` are renames history cannot see yet, mapping a path at ``rev``
    to its new name; ``ensure_paths`` are current paths kept as live coupling
    partners even when the tree at ``rev`` lacks them. Renames are collected
    from the full history, bulk commits included, so a rename inside a bulk
    commit still joins a file's older and newer names.

    Raises:
        NotAGitRepoError: If repo_path is not a git repository.
        GitToolNotFoundError: If the git binary is not installed.
    """
    aliases = aliases or {}
    full_history = fetch_git_history(repo_path, days, rev, aliases=aliases)
    renamed_from = _former_paths_by_path(full_history)
    commits, ignored = exclude_bulk(full_history, policy.max_changeset_size)
    live_paths = (
        head_paths(repo_path, rev or "HEAD") | ensure_paths | frozenset(aliases.values())
        if policy.require_live_partner and commits
        else None
    )
    return HistoryWindow(
        commits=commits,
        ignored_bulk_commits=ignored,
        live_paths=live_paths,
        renamed_from=renamed_from,
        aliases=_rename_aliases(full_history, renamed_from) | aliases,
    )


def _former_paths_by_path(commits: list[Commit]) -> dict[str, list[str]]:
    """Collect every earlier name each current path had across the history."""
    former: dict[str, set[str]] = defaultdict(set)
    for commit in commits:
        for file in commit.files:
            former[file.path].update(file.former_paths)
    return {path: sorted(names - {path}) for path, names in former.items() if names - {path}}


def _rename_aliases(commits: list[Commit], renamed_from: dict[str, list[str]]) -> dict[str, str]:
    """Map each earlier name to its current path, skipping names a current file still uses."""
    current_paths = {file.path for commit in commits for file in commit.files}
    return {
        name: path
        for path, names in renamed_from.items()
        for name in names
        if name not in current_paths
    }
