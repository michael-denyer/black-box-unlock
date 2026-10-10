"""Real-Git verification that ownership counts people, not aliases or bots."""

import os
import subprocess

from black_box_unlock.git.log import fetch_git_history
from black_box_unlock.git.ownership import parse_ownership_from_history


def _commit(repo, author: str, email: str, message: str) -> None:
    environment = {
        **os.environ,
        "GIT_AUTHOR_NAME": author,
        "GIT_AUTHOR_EMAIL": email,
        "GIT_COMMITTER_NAME": "Committer",
        "GIT_COMMITTER_EMAIL": "committer@example.com",
    }
    with (repo / "a.py").open("a") as handle:
        handle.write(f"# {message}\n")
    for args in (["add", "."], ["commit", "-m", message]):
        subprocess.run(
            ["git", "-C", str(repo), *args], check=True, capture_output=True, env=environment
        )


def test_mailmap_aliases_and_bots_are_not_extra_authors(tmp_path):
    subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
    (tmp_path / ".mailmap").write_text("Alice <alice@work.com> <alice@home.com>\n")
    _commit(tmp_path, "Alice", "alice@work.com", "one")
    _commit(tmp_path, "Alice", "alice@home.com", "two")
    _commit(
        tmp_path,
        "dependabot[bot]",
        "49699333+dependabot[bot]@users.noreply.github.com",
        "three",
    )
    _commit(tmp_path, "GitHub", "noreply@github.com", "four")

    ownership = parse_ownership_from_history(fetch_git_history(tmp_path, 30))

    a_py = next(item for item in ownership if item.path == "a.py")
    assert a_py.authors == ["alice@work.com"]
    assert a_py.commits == 4
