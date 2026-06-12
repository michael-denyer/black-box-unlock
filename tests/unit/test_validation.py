"""Unit tests for hotspot-vs-bugfix self-validation."""

from datetime import datetime, timezone

import pytest

from black_box_unlock.validation import spearman_rho, split_history


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
