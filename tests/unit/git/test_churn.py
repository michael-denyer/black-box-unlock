"""Tests for file churn extraction."""

import json
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest

from black_box_unlock.core.exceptions import NotAGitRepoError
from black_box_unlock.git.churn import extract_file_churn, parse_history_entries


@pytest.fixture
def sample_gmap_output():
    """Load sample gmap JSON output."""
    fixture_path = Path(__file__).parent.parent.parent / "fixtures" / "sample_gmap_output.json"
    return json.loads(fixture_path.read_text())


class TestParseHistoryEntries:
    """Tests for parsing git history entries into FileChurn."""

    def test_aggregates_churn_per_file(self, sample_gmap_output):
        """Aggregates commits and line changes per file."""
        result = parse_history_entries(sample_gmap_output)

        # src/main.py appears in 2 commits
        main_py = next(f for f in result if f.path == "src/main.py")
        assert main_py.commits == 2
        assert main_py.lines_added == 70  # 50 + 20
        assert main_py.lines_deleted == 15  # 10 + 5

        # src/utils.py appears in 1 commit
        utils_py = next(f for f in result if f.path == "src/utils.py")
        assert utils_py.commits == 1
        assert utils_py.lines_added == 30
        assert utils_py.lines_deleted == 0

    def test_tracks_first_and_last_commit_dates(self, sample_gmap_output):
        """Tracks first and last commit timestamps per file."""
        result = parse_history_entries(sample_gmap_output)

        main_py = next(f for f in result if f.path == "src/main.py")
        assert main_py.first_commit == datetime(2026, 1, 20, 10, 0, 0)
        assert main_py.last_commit == datetime(2026, 1, 25, 10, 0, 0)

    def test_returns_empty_list_for_no_entries(self):
        """Returns empty list when no commits."""
        data = {"version": 1, "entries": []}
        result = parse_history_entries(data)
        assert result == []


class TestExtractFileChurn:
    """Tests for extract_file_churn function."""

    def test_calls_git_with_correct_args(self, tmp_path):
        """Calls git log with repo path and since flag."""
        # Create fake git repo
        (tmp_path / ".git").mkdir()

        with patch("black_box_unlock.git.log.subprocess.run") as mock_run:
            mock_run.return_value.stdout = ""
            mock_run.return_value.returncode = 0

            extract_file_churn(tmp_path, since_days=30)

            mock_run.assert_called_once()
            call_args = mock_run.call_args[0][0]
            assert "git" in call_args
            assert str(tmp_path) in call_args
            assert "--since=30 days ago" in call_args

    def test_raises_not_a_git_repo_error(self, tmp_path):
        """Raises NotAGitRepoError when path is not a git repo."""
        # tmp_path has no .git directory
        with pytest.raises(NotAGitRepoError) as exc_info:
            extract_file_churn(tmp_path)

        assert str(tmp_path) in str(exc_info.value)
