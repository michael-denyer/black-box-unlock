"""Real-Git verification for change-selection layer semantics."""

import os
import subprocess

from black_box_unlock.git.changes import (
    BaseChange,
    StagedChange,
    WorkingTreeChange,
    collect_change_set,
)
from black_box_unlock.review import ChangeReview, run_change_review


def _git(repo, *args: str) -> None:
    environment = {
        **os.environ,
        "GIT_AUTHOR_NAME": "Alice",
        "GIT_AUTHOR_EMAIL": "alice@example.com",
        "GIT_COMMITTER_NAME": "Alice",
        "GIT_COMMITTER_EMAIL": "alice@example.com",
    }
    subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        env=environment,
    )


def test_base_staged_and_working_tree_modes_isolate_layers(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    (repo / "branch.py").write_text("base = 1\n")
    (repo / "staged.py").write_text("base = 1\n")
    (repo / "unstaged.py").write_text("base = 1\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "base")
    _git(repo, "tag", "review-base")

    (repo / "branch.py").write_text("branch = 2\n")
    _git(repo, "add", "branch.py")
    _git(repo, "commit", "-m", "branch change")
    (repo / "staged.py").write_text("staged = 2\n")
    _git(repo, "add", "staged.py")
    (repo / "unstaged.py").write_text("unstaged = 2\n")
    (repo / "untracked.py").write_text("untracked = 1\n")

    staged = collect_change_set(repo, StagedChange())
    working = collect_change_set(repo, WorkingTreeChange())
    base = collect_change_set(repo, BaseChange(base_ref="review-base"))

    assert [path.path for path in staged.paths] == ["staged.py"]
    assert [path.path for path in working.paths] == ["unstaged.py", "untracked.py"]
    assert [path.path for path in base.paths] == [
        "branch.py",
        "staged.py",
        "unstaged.py",
        "untracked.py",
    ]


def test_working_tree_reviews_untracked_files_before_the_first_commit(tmp_path):
    repo = tmp_path / "unborn"
    repo.mkdir()
    _git(repo, "init")
    (repo / "new.py").write_text("value = 1\n")

    result = collect_change_set(repo, WorkingTreeChange())

    assert result.provenance.head_oid is None
    assert [path.path for path in result.paths] == ["new.py"]

    review = run_change_review(repo, WorkingTreeChange())

    assert isinstance(review, ChangeReview)
    assert review.files[0].evidence.path == "new.py"
    assert review.files[0].evidence.commits == 0

    _git(repo, "add", "new.py")
    staged = collect_change_set(repo, StagedChange())

    assert staged.provenance.head_oid is None
    assert [path.path for path in staged.paths] == ["new.py"]
