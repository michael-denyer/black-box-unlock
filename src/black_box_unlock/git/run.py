"""Single entry point for checked git subprocess calls.

Centralizes the three things every git invocation in this package needs: the
not-a-repo guard, the git-missing mapping, and the unborn-HEAD tolerance.
"""

import subprocess
from pathlib import Path

from ..core.exceptions import GitToolNotFoundError, NotAGitRepoError

_UNBORN_HEAD_MARKERS = ("does not have any commits", "bad default revision")


def run_git(
    repo_path: Path,
    args: list[str],
    *,
    config: list[str] | None = None,
    tolerate_unborn: bool = False,
) -> str:
    """Run a checked git command in repo_path and return stdout.

    Always passes core.quotePath=false so non-ASCII paths survive; extra ``-c``
    settings go in ``config``. With ``tolerate_unborn``, an unborn-HEAD repo
    (freshly init'd, no commits) yields "" instead of raising.

    Raises:
        NotAGitRepoError: If repo_path is not a git repository.
        GitToolNotFoundError: If the git binary is not installed.
    """
    if not (repo_path / ".git").exists():
        raise NotAGitRepoError(f"Not a git repository: {repo_path}")

    cmd = ["git", "-c", "core.quotePath=false"]
    for setting in config or []:
        cmd += ["-c", setting]
    cmd += ["-C", str(repo_path), *args]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    except FileNotFoundError as e:
        raise GitToolNotFoundError("git not found on PATH") from e
    except subprocess.CalledProcessError as e:
        if (
            tolerate_unborn
            and e.returncode == 128
            and any(m in e.stderr for m in _UNBORN_HEAD_MARKERS)
        ):
            return ""
        raise
    return result.stdout
