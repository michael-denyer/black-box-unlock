"""Tests for file churn extraction."""

import json
from datetime import datetime
from pathlib import Path

import pytest

from black_box_unlock.git.churn import parse_history_entries
from black_box_unlock.git.log import Commit


@pytest.fixture
def sample_history():
    """Load sample git history JSON as typed Commit models."""
    fixture_path = Path(__file__).parent.parent.parent / "fixtures" / "sample_history.json"
    raw = json.loads(fixture_path.read_text())
    return [Commit(**entry) for entry in raw["entries"]]


class TestParseHistoryEntries:
    """Tests for parsing git history entries into FileChurn."""

    def test_aggregates_churn_per_file(self, sample_history):
        """Aggregates commits and line changes per file."""
        result = parse_history_entries(sample_history)

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

    def test_tracks_first_and_last_commit_dates(self, sample_history):
        """Tracks first and last commit timestamps per file."""
        result = parse_history_entries(sample_history)

        main_py = next(f for f in result if f.path == "src/main.py")
        assert main_py.first_commit == datetime(2026, 1, 20, 10, 0, 0)
        assert main_py.last_commit == datetime(2026, 1, 25, 10, 0, 0)

    def test_returns_empty_list_for_no_entries(self):
        """Returns empty list when no commits."""
        assert parse_history_entries([]) == []
