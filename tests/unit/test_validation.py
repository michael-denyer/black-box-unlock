"""Unit tests for hotspot-vs-bugfix self-validation."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from black_box_unlock.core.exceptions import InsufficientHistoryError
from black_box_unlock.validation import spearman_rho, split_history, validate_repo

INDENTED = "def f(x):\n    if x:\n        return 1\n    return 0\n"
FLAT = "X = 1\nY = 2\n"


def _days_ago(n: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=n)).isoformat()


def _entry(timestamp: str, message: str = "feat: x", paths: list[str] | None = None) -> dict:
    return {
        "timestamp": timestamp,
        "author_email": "a@x.com",
        "message": message,
        "files": [{"path": p, "added_lines": 1, "deleted_lines": 0} for p in (paths or ["a.py"])],
    }


class TestSpearmanRho:
    def test_perfect_monotonic_is_one(self):
        assert spearman_rho([1, 2, 3, 4], [10, 20, 30, 40]) == pytest.approx(1.0)

    def test_perfect_inverse_is_minus_one(self):
        assert spearman_rho([1, 2, 3, 4], [40, 30, 20, 10]) == pytest.approx(-1.0)

    def test_nonlinear_monotonic_is_still_one(self):
        # rank correlation ignores scale: x vs x**3 is perfectly monotonic
        assert spearman_rho([1, 2, 3, 4], [1, 8, 27, 64]) == pytest.approx(1.0)

    def test_ties_use_average_ranks(self):
        # ys has a tie; scipy.stats.spearmanr gives 0.9486832980505138 here
        rho = spearman_rho([1, 2, 3, 4], [10, 20, 20, 30])
        assert rho == pytest.approx(0.9486832980505138)

    def test_constant_input_returns_none(self):
        assert spearman_rho([1, 2, 3], [5, 5, 5]) is None

    def test_fewer_than_two_points_returns_none(self):
        assert spearman_rho([1], [2]) is None


class TestSplitHistory:
    CUTOFF = datetime(2026, 3, 1, tzinfo=timezone.utc)

    def test_partitions_entries_at_cutoff(self):
        history = {
            "entries": [
                _entry("2026-05-01T10:00:00+00:00"),
                _entry("2026-01-01T10:00:00+00:00"),
            ]
        }
        train, test = split_history(history, self.CUTOFF)
        assert [e["timestamp"] for e in train["entries"]] == ["2026-01-01T10:00:00+00:00"]
        assert [e["timestamp"] for e in test["entries"]] == ["2026-05-01T10:00:00+00:00"]

    def test_entry_exactly_at_cutoff_goes_to_test(self):
        history = {"entries": [_entry("2026-03-01T00:00:00+00:00")]}
        train, test = split_history(history, self.CUTOFF)
        assert train["entries"] == []
        assert len(test["entries"]) == 1

    def test_zulu_suffix_timestamps_parse(self):
        # git %aI emits +00:00 offsets but fixtures and other tools use Z
        history = {"entries": [_entry("2026-01-01T10:00:00Z")]}
        train, test = split_history(history, self.CUTOFF)
        assert len(train["entries"]) == 1
        assert test["entries"] == []

    def test_empty_history(self):
        train, test = split_history({"entries": []}, self.CUTOFF)
        assert train["entries"] == []
        assert test["entries"] == []


def _fake_history() -> dict:
    # Train half (older than the 50-day cutoff for days=100, split=0.5):
    # hot.py churns 3x, cold.py once. Test half: 2 bugfix commits touch hot.py.
    return {
        "entries": [
            _entry(_days_ago(90), "feat: a", ["hot.py"]),
            _entry(_days_ago(80), "feat: b", ["hot.py", "cold.py"]),
            _entry(_days_ago(70), "feat: c", ["hot.py", "gone.py"]),
            _entry(_days_ago(30), "fix: crash", ["hot.py"]),
            _entry(_days_ago(10), "fix: regression", ["hot.py"]),
        ]
    }


class TestValidateRepo:
    def _run(self, tmp_path: Path):
        (tmp_path / "hot.py").write_text(INDENTED)
        (tmp_path / "cold.py").write_text(FLAT)
        # gone.py intentionally absent: deleted files drop out of the universe
        with patch("black_box_unlock.validation.fetch_git_history") as mock_fetch:
            mock_fetch.return_value = _fake_history()
            return validate_repo(tmp_path, days=100, split=0.5)

    def test_correlates_train_hotspots_with_test_bugfixes(self, tmp_path):
        result = self._run(tmp_path)
        assert result.spearman == pytest.approx(1.0)  # hot.py: top score, all fixes

    def test_universe_excludes_deleted_files(self, tmp_path):
        result = self._run(tmp_path)
        assert result.file_count == 2  # hot.py, cold.py — not gone.py

    def test_top_decile_share_counts_bugfix_touches(self, tmp_path):
        # universe of 2 -> top decile is ceil(0.2)=1 file (hot.py) with all touches
        result = self._run(tmp_path)
        assert result.top_decile_share == pytest.approx(1.0)
        assert result.test_bugfix_touches == 2

    def test_coverage_is_full_when_all_fixes_hit_ranked_files(self, tmp_path):
        result = self._run(tmp_path)
        assert result.bugfix_coverage == pytest.approx(1.0)

    def test_no_test_window_bugfixes_yields_none_share(self, tmp_path):
        (tmp_path / "hot.py").write_text(INDENTED)
        history = {
            "entries": [
                _entry(_days_ago(90), "feat: a", ["hot.py"]),
                _entry(_days_ago(10), "feat: quiet period", ["hot.py"]),
            ]
        }
        with patch("black_box_unlock.validation.fetch_git_history") as mock_fetch:
            mock_fetch.return_value = history
            result = validate_repo(tmp_path, days=100, split=0.5)
        assert result.top_decile_share is None
        assert result.bugfix_coverage is None

    def test_empty_train_half_raises(self, tmp_path):
        (tmp_path / "hot.py").write_text(INDENTED)
        history = {"entries": [_entry(_days_ago(10), "feat: a", ["hot.py"])]}
        with patch("black_box_unlock.validation.fetch_git_history") as mock_fetch:
            mock_fetch.return_value = history
            with pytest.raises(InsufficientHistoryError):
                validate_repo(tmp_path, days=100, split=0.5)

    def test_empty_test_half_raises(self, tmp_path):
        (tmp_path / "hot.py").write_text(INDENTED)
        history = {"entries": [_entry(_days_ago(90), "feat: a", ["hot.py"])]}
        with patch("black_box_unlock.validation.fetch_git_history") as mock_fetch:
            mock_fetch.return_value = history
            with pytest.raises(InsufficientHistoryError):
                validate_repo(tmp_path, days=100, split=0.5)
