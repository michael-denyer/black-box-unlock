"""Unit tests for hotspot-vs-bugfix self-validation."""

from datetime import datetime, timezone

import pytest

from black_box_unlock.git.log import Commit
from black_box_unlock.validation import (
    permutation_p,
    score_ranking,
    spearman_rho,
    split_history,
)
from tests.factories import make_commit


def _entry(timestamp: str, message: str = "feat: x", paths: list[str] | None = None) -> Commit:
    return make_commit(paths or ["a.py"], timestamp=timestamp, message=message)


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
        history = [
            _entry("2026-05-01T10:00:00+00:00"),
            _entry("2026-01-01T10:00:00+00:00"),
        ]
        train, test = split_history(history, self.CUTOFF)
        assert [c.timestamp for c in train] == [datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc)]
        assert [c.timestamp for c in test] == [datetime(2026, 5, 1, 10, 0, tzinfo=timezone.utc)]

    def test_entry_exactly_at_cutoff_goes_to_test(self):
        history = [_entry("2026-03-01T00:00:00+00:00")]
        train, test = split_history(history, self.CUTOFF)
        assert train == []
        assert len(test) == 1

    def test_zulu_suffix_timestamps_parse(self):
        # git %aI emits +00:00 offsets but fixtures and other tools use Z
        history = [_entry("2026-01-01T10:00:00Z")]
        train, test = split_history(history, self.CUTOFF)
        assert len(train) == 1
        assert test == []

    def test_empty_history(self):
        train, test = split_history([], self.CUTOFF)
        assert train == []
        assert test == []


class TestPermutationP:
    def test_counts_draws_at_or_above_observed_with_plus_one_correction(self):
        # one of four draws ties the observed share: (1 + 1) / (4 + 1)
        assert permutation_p(0.5, [0.5, 0.0, 0.0, 0.0]) == pytest.approx(0.4)

    def test_observed_above_every_draw_is_the_floor_not_zero(self):
        assert permutation_p(1.0, [0.0] * 199) == pytest.approx(1 / 200)

    def test_undefined_observed_share_gives_none(self):
        assert permutation_p(None, [0.1, 0.2]) is None


class TestScoreRanking:
    SCORES = {"hot.py": 9.0, "warm.py": 4.0, "cold.py": 1.0, "zero.py": 0.0}

    def test_top_decile_is_the_ceiling_of_ten_percent(self):
        # four files -> ceil(0.4) = 1 top file, which takes 2 of 3 touches
        result = score_ranking(self.SCORES, {"hot.py": 2, "cold.py": 1})
        assert result.top_files == ["hot.py"]
        assert result.top_decile_share == pytest.approx(2 / 3)

    def test_spearman_pairs_scores_with_touches_in_universe_order(self):
        result = score_ranking(self.SCORES, {"hot.py": 3, "warm.py": 2, "cold.py": 1})
        assert result.spearman == pytest.approx(1.0)

    def test_no_touches_yields_none_share(self):
        result = score_ranking(self.SCORES, {})
        assert result.top_decile_share is None

    def test_ties_break_on_path_so_top_files_are_deterministic(self):
        result = score_ranking({"b.py": 1.0, "a.py": 1.0}, {})
        assert result.top_files == ["a.py"]
