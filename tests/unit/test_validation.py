"""Unit tests for hotspot-vs-bugfix self-validation."""

import pytest

from black_box_unlock.validation import (
    permutation_p,
    score_ranking,
    spearman_rho,
)


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

    def test_boundary_ties_share_the_top_slots_pro_rata(self):
        # twenty files -> two top slots. a.py holds one outright; b.py and c.py
        # tie for the other, so each gets half credit: 2 + (0 + 2) / 2 = 3 of 4.
        # Breaking the tie on path would credit b.py alone and report 2 of 4.
        scores = {"a.py": 9.0, "b.py": 5.0, "c.py": 5.0}
        scores.update({f"z{i}.py": 0.0 for i in range(17)})
        result = score_ranking(scores, {"a.py": 2, "c.py": 2})
        assert result.top_decile_share == pytest.approx(3 / 4)

    def test_all_tied_at_the_boundary_credits_the_average(self):
        # ten files, one slot, all scores equal: the slot takes 1/10 of every touch
        scores = {f"f{i}.py": 1.0 for i in range(10)}
        result = score_ranking(scores, {"f9.py": 5})
        assert result.top_decile_share == pytest.approx(0.1)
