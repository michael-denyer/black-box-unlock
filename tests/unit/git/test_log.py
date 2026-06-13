"""Unit tests for native git history extraction."""

import os
import subprocess
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from black_box_unlock.core.exceptions import GitToolNotFoundError, NotAGitRepoError
from black_box_unlock.git.log import Commit, CommitFile, _parse_log_output, fetch_git_history

# \x01 marks a commit record; fields are tab-separated: iso-date, email, subject
SAMPLE_LOG = (
    "\x012026-01-20T10:00:00+00:00\talice@example.com\tfeat: add auth\n"
    "100\t20\tsrc/auth.py\n"
    "50\t10\tsrc/user.py\n"
    "\n"
    "\x012026-01-21T10:00:00+00:00\tbob@example.com\tfix: token bug\n"
    "30\t5\tsrc/auth.py\n"
    "-\t-\tassets/logo.png\n"
)


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
