"""Unit tests for native git history extraction."""

import os
import subprocess
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from black_box_unlock.core.exceptions import GitToolNotFoundError, NotAGitRepoError
from black_box_unlock.git.log import Commit, CommitFile, _parse_log_output, fetch_git_history

# git log -z: \x01 marks a commit record whose header (iso-date, email, subject,
# tab-separated) ends in a newline; numstat records end in NUL, commits in NUL.
SAMPLE_LOG = (
    "\x012026-01-20T10:00:00+00:00\talice@example.com\tfeat: add auth\n"
    "100\t20\tsrc/auth.py\0"
    "50\t10\tsrc/user.py\0"
    "\0"
    "\x012026-01-21T10:00:00+00:00\tbob@example.com\tfix: token bug\n"
    "30\t5\tsrc/auth.py\0"
    "-\t-\tassets/logo.png\0"
)


def _record(day: int, *entries: str) -> str:
    """One -z commit record; a rename entry is 'added\\tdeleted\\t\\0old\\0new'."""
    header = f"\x012026-01-{day:02d}T10:00:00+00:00\tdev@example.com\tchange {day}\n"
    return header + "".join(f"{entry}\0" for entry in entries) + "\0"


def _paths(commits: list[Commit]) -> list[list[tuple[str, list[str]]]]:
    return [[(file.path, file.former_paths) for file in commit.files] for commit in commits]


class TestRenameFollowing:
    def test_older_commits_report_the_renamed_files_current_path(self):
        """History before a rename lands on the new path, with the old name kept."""
        log = (
            _record(3, "1\t1\tsrc/b.py")
            + _record(2, "0\t0\t\0src/a.py\0src/b.py")
            + _record(1, "4\t2\tsrc/a.py", "1\t0\tsrc/partner.py")
        )

        assert _paths(_parse_log_output(log)) == [
            [("src/b.py", [])],
            [("src/b.py", ["src/a.py"])],
            [("src/b.py", ["src/a.py"]), ("src/partner.py", [])],
        ]

    def test_chained_renames_collapse_to_the_final_path(self):
        log = (
            _record(3, "0\t0\t\0b.py\0c.py")
            + _record(2, "0\t0\t\0a.py\0b.py")
            + _record(1, "3\t0\ta.py")
        )

        assert _paths(_parse_log_output(log)) == [
            [("c.py", ["b.py"])],
            [("c.py", ["a.py", "b.py"])],
            [("c.py", ["a.py"])],
        ]

    def test_a_path_reused_after_a_rename_stays_a_separate_file(self):
        """A new file created at the old name keeps its own history."""
        log = (
            _record(3, "2\t0\told.py")
            + _record(2, "0\t0\t\0old.py\0new.py")
            + _record(1, "5\t0\told.py")
        )

        assert _paths(_parse_log_output(log)) == [
            [("old.py", [])],
            [("new.py", ["old.py"])],
            [("new.py", ["old.py"])],
        ]

    def test_a_binary_rename_still_redirects_older_history(self):
        log = _record(2, "-\t-\t\0logo.bin\0art.bin") + _record(1, "1\t0\tlogo.bin")

        assert _paths(_parse_log_output(log)) == [[], [("art.bin", ["logo.bin"])]]

    def test_renames_in_one_commit_resolve_against_the_names_before_it(self):
        """Shifting a.py to b.py and b.py to c.py in one commit keeps two files apart."""
        log = _record(3, "0\t0\t\0b.py\0c.py", "0\t0\t\0a.py\0b.py") + _record(
            2, "1\t1\ta.py", "2\t2\tb.py"
        )

        assert _paths(_parse_log_output(log))[1] == [("b.py", ["a.py"]), ("c.py", ["b.py"])]

    def test_follows_a_real_git_mv(self, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()

        def git(*args: str) -> None:
            subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)

        git("init")
        git("config", "user.email", "dev@example.com")
        git("config", "user.name", "Dev")
        (repo / "old name.py").write_text("value = 1\n")
        git("add", ".")
        git("commit", "-m", "add")
        git("mv", "old name.py", "new name.py")
        git("commit", "-m", "rename")

        commits = fetch_git_history(repo, days=30)

        assert _paths(commits) == [
            [("new name.py", ["old name.py"])],
            [("new name.py", ["old name.py"])],
        ]
        assert commits[0].files[0].added_lines == 0


class TestParseLogOutput:
    def test_parses_commits_into_typed_models(self):
        """Each commit becomes a Commit with a parsed timestamp, author, message, files."""
        commits = _parse_log_output(SAMPLE_LOG)

        assert len(commits) == 2
        first = commits[0]
        assert first.timestamp == datetime(2026, 1, 20, 10, 0, 0, tzinfo=timezone.utc)
        assert first.author_email == "alice@example.com"
        assert first.message == "feat: add auth"
        assert first.files == [
            CommitFile(path="src/auth.py", added_lines=100, deleted_lines=20),
            CommitFile(path="src/user.py", added_lines=50, deleted_lines=10),
        ]

    def test_skips_binary_files(self):
        """Binary numstat lines (- as counts) are skipped."""
        commits = _parse_log_output(SAMPLE_LOG)

        assert commits[1].files == [CommitFile(path="src/auth.py", added_lines=30, deleted_lines=5)]

    def test_empty_log_gives_empty_list(self):
        assert _parse_log_output("") == []


class TestFetchGitHistory:
    def test_raises_not_a_git_repo(self, tmp_path):
        with pytest.raises(NotAGitRepoError):
            fetch_git_history(tmp_path, days=30)

    @patch("black_box_unlock.git.run.subprocess.run")
    def test_raises_git_tool_not_found(self, mock_run, tmp_path):
        (tmp_path / ".git").mkdir()
        mock_run.side_effect = FileNotFoundError(2, "No such file or directory", "git")

        with pytest.raises(GitToolNotFoundError):
            fetch_git_history(tmp_path, days=30)

    @patch("black_box_unlock.git.run.subprocess.run")
    def test_invokes_git_log_with_since_window(self, mock_run, tmp_path):
        (tmp_path / ".git").mkdir()
        mock_run.return_value.stdout = SAMPLE_LOG

        commits = fetch_git_history(tmp_path, days=45)

        cmd = mock_run.call_args[0][0]
        assert cmd[0] == "git"
        assert "core.quotePath=false" in cmd
        assert "-C" in cmd
        assert str(tmp_path) == cmd[cmd.index("-C") + 1]
        assert "--since=45 days ago" in cmd
        assert "--numstat" in cmd
        assert len(commits) == 2

    @patch("black_box_unlock.git.run.subprocess.run")
    def test_rev_ends_history_at_that_revision(self, mock_run, tmp_path):
        (tmp_path / ".git").mkdir()
        mock_run.return_value.stdout = SAMPLE_LOG

        fetch_git_history(tmp_path, days=45, rev="abc123..HEAD")

        cmd = mock_run.call_args[0][0]
        assert cmd[-1] == "abc123..HEAD"

    def test_unicode_paths_are_preserved(self, tmp_path):
        """Git core.quotePath=true would mangle non-ASCII paths; we must pass -c core.quotePath=false."""
        git_env = {
            "GIT_AUTHOR_NAME": "A",
            "GIT_AUTHOR_EMAIL": "a@x.com",
            "GIT_COMMITTER_NAME": "A",
            "GIT_COMMITTER_EMAIL": "a@x.com",
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "HOME": str(tmp_path),
        }
        subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True, env=git_env)
        subprocess.run(
            ["git", "-C", str(tmp_path), "config", "user.email", "a@x.com"],
            check=True,
            capture_output=True,
            env=git_env,
        )
        subprocess.run(
            ["git", "-C", str(tmp_path), "config", "user.name", "A"],
            check=True,
            capture_output=True,
            env=git_env,
        )
        unicode_file = tmp_path / "café.py"
        unicode_file.write_text("pass\n")
        subprocess.run(
            ["git", "-C", str(tmp_path), "add", "café.py"],
            check=True,
            capture_output=True,
            env=git_env,
        )
        subprocess.run(
            ["git", "-C", str(tmp_path), "commit", "-m", "add unicode file"],
            check=True,
            capture_output=True,
            env=git_env,
        )

        commits = fetch_git_history(tmp_path, days=30)

        assert len(commits) == 1
        paths = [f.path for f in commits[0].files]
        assert "café.py" in paths

    def test_empty_repo_returns_empty_list(self, tmp_path):
        """A freshly git-init'd repo with no commits should return an empty list, not raise."""
        git_env = {
            "GIT_AUTHOR_NAME": "A",
            "GIT_AUTHOR_EMAIL": "a@x.com",
            "GIT_COMMITTER_NAME": "A",
            "GIT_COMMITTER_EMAIL": "a@x.com",
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "HOME": str(tmp_path),
        }
        subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True, env=git_env)

        assert fetch_git_history(tmp_path, days=30) == []


class TestCommitModel:
    def test_parses_zulu_and_offset_timestamps(self):
        """git emits +00:00; fixtures and other tools emit Z. Both must parse at the boundary."""
        assert Commit(timestamp="2026-01-01T10:00:00Z").timestamp == datetime(
            2026, 1, 1, 10, 0, 0, tzinfo=timezone.utc
        )
        assert Commit(timestamp="2026-01-01T10:00:00+00:00").timestamp == datetime(
            2026, 1, 1, 10, 0, 0, tzinfo=timezone.utc
        )

    def test_defaults_keep_optional_fields_absent(self):
        """author_email/message/files default empty so non-churn callers can omit them."""
        commit = Commit(timestamp="2026-01-01T10:00:00Z")
        assert commit.author_email == ""
        assert commit.message == ""
        assert commit.files == []
