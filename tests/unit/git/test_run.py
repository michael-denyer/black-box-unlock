"""Tests for the shared git helpers."""

import subprocess
from pathlib import Path

import pytest

from black_box_unlock.core.exceptions import NotAGitRepoError, RepositoryPathError
from black_box_unlock.git.run import head_oid, relative_to_repo, run_git_bytes


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    (repo / "src").mkdir()
    (repo / "src" / "a.py").write_text("x = 1\n")
    (repo / "link.py").symlink_to("src/a.py")
    return repo


class TestRelativeToRepo:
    def test_relative_and_absolute_spellings_give_one_record(self, repo):
        assert relative_to_repo(repo, "src/a.py") == "src/a.py"
        assert relative_to_repo(repo, str(repo / "src" / "a.py")) == "src/a.py"
        assert relative_to_repo(repo, "src/../src/./a.py") == "src/a.py"

    def test_path_through_a_symlinked_parent_directory_is_accepted(self, repo, tmp_path):
        alias = tmp_path / "alias"
        alias.symlink_to(repo, target_is_directory=True)

        assert relative_to_repo(repo, str(alias / "src" / "a.py")) == "src/a.py"
        assert relative_to_repo(alias, str(repo / "src" / "a.py")) == "src/a.py"

    def test_tracked_symlink_keeps_its_own_path(self, repo):
        assert relative_to_repo(repo, "link.py") == "link.py"

    @pytest.mark.parametrize("path", ["../elsewhere.py", "/definitely/elsewhere.py"])
    def test_path_outside_the_repository_raises(self, repo, path):
        with pytest.raises(RepositoryPathError, match="outside the repository"):
            relative_to_repo(repo, path)

    @pytest.mark.parametrize("path", [".", "src"])
    def test_directory_raises(self, repo, path):
        with pytest.raises(RepositoryPathError, match="is a directory"):
            relative_to_repo(repo, path)


class TestHeadOid:
    def test_unborn_repository_has_no_head(self, repo):
        assert head_oid(repo) is None

    def test_commit_resolves_to_a_full_oid_and_unknown_refs_to_none(self, repo):
        _git(repo, "add", ".")
        _git(repo, "-c", "user.name=T", "-c", "user.email=t@example.com", "commit", "-m", "init")

        oid = head_oid(repo)

        assert oid is not None and len(oid) == 40
        assert head_oid(repo, "nope") is None


class TestRunGitBytes:
    def test_feeds_stdin_and_returns_raw_stdout(self, repo):
        (repo / "src" / "blob.bin").write_bytes(b"\xff\x00raw\n")
        _git(repo, "add", "src/blob.bin")
        _git(repo, "-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-m", "blob")

        output = run_git_bytes(repo, ["cat-file", "--batch"], stdin=b"HEAD:src/blob.bin\n")

        header, _, body = output.partition(b"\n")
        assert header.split(b" ")[1:] == [b"blob", b"6"]
        assert body == b"\xff\x00raw\n\n"

    def test_missing_repository_is_refused_before_git_runs(self, tmp_path):
        with pytest.raises(NotAGitRepoError):
            run_git_bytes(tmp_path, ["cat-file", "--batch"])
