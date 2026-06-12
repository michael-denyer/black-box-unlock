"""Unit tests for hotspot-vs-bugfix self-validation."""

import pytest

from black_box_unlock.validation import spearman_rho


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
