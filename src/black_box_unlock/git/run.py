"""Single entry point for checked git subprocess calls.

Centralizes the three things every git invocation in this package needs: the
not-a-repo guard, the git-missing mapping, and the unborn-HEAD tolerance.
"""

import subprocess
from pathlib import Path

from ..core.exceptions import GitToolNotFoundError, NotAGitRepoError

_UNBORN_HEAD_MARKERS = ("does not have any commits", "bad default revision")


def repo_toplevel(path: Path) -> Path:
    """Return the working-tree root that contains path, asking git rather than looking for .git.

    Works from subdirectories and linked worktrees, where run_git's
    ``.git`` check does not hold.

    Raises:
        NotAGitRepoError: If path is not inside a git working tree.
        GitToolNotFoundError: If the git binary is not installed.
    """
    cmd = ["git", "-C", str(path), "rev-parse", "--show-toplevel"]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    except FileNotFoundError as e:
        raise GitToolNotFoundError("git not found on PATH") from e
    except subprocess.CalledProcessError as e:
        raise NotAGitRepoError(f"Not a git repository: {path}: {e.stderr.strip()}") from e
    return Path(result.stdout.strip())


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


def head_oid(repo_path: Path, rev: str = "HEAD") -> str | None:
    """Return the full oid of rev (HEAD by default), or None when rev names no commit.

    An unborn HEAD makes git say "unknown revision", which is not one of the
    unborn markers run_git tolerates, so the verify failure is caught here.
    """
    try:
        return run_git(repo_path, ["rev-parse", "--verify", f"{rev}^{{commit}}"]).strip() or None
    except subprocess.CalledProcessError:
        return None


def is_shallow(repo_path: Path) -> bool:
    """Return True when the repository is a shallow clone."""
    return run_git(repo_path, ["rev-parse", "--is-shallow-repository"]).strip() == "true"


def head_paths(repo_path: Path, rev: str = "HEAD") -> frozenset[str]:
    """Return every repo-relative file path in the tree at rev (HEAD by default).

    Raises:
        NotAGitRepoError: If repo_path is not a git repository.
        GitToolNotFoundError: If the git binary is not installed.
    """
    output = run_git(repo_path, ["ls-tree", "-r", "--name-only", "--full-tree", rev])
    return frozenset(output.splitlines())
