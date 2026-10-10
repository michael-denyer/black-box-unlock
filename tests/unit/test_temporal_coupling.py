"""Unit tests for temporal coupling detection."""

from black_box_unlock.core.models import CouplingPolicy, TemporalCoupling
from black_box_unlock.git.coupling import analyze_temporal_coupling
from black_box_unlock.git.log import exclude_bulk
from tests.factories import make_commit


def _pairs(history, min_ratio=0.0, min_shared_revisions=1, live_paths=None):
    policy = CouplingPolicy(min_ratio=min_ratio, min_shared_revisions=min_shared_revisions)
    return analyze_temporal_coupling(history, policy, live_paths).couplings


class TestTemporalCouplingModel:
    """Tests for TemporalCoupling data model."""

    def test_creates_coupling_with_required_fields(self):
        """Creates a TemporalCoupling with all required fields."""
        coupling = TemporalCoupling(
            file_a="src/auth.py",
            file_b="src/user.py",
            co_change_count=4,
            commits_a=10,
            commits_b=5,
        )

        assert coupling.file_a == "src/auth.py"
        assert coupling.file_b == "src/user.py"
        assert coupling.co_change_count == 4
        assert coupling.commits_a == 10
        assert coupling.commits_b == 5

    def test_coupling_ratio_uses_min_commits(self):
        """Coupling ratio divides by minimum of commits_a and commits_b."""
        coupling = TemporalCoupling(
            file_a="a.py",
            file_b="b.py",
            co_change_count=4,
            commits_a=10,
            commits_b=5,
        )

        # 4 / min(10, 5) = 4/5 = 0.8
        assert coupling.coupling_ratio == 0.8

    def test_coupling_ratio_returns_zero_when_no_commits(self):
        """Coupling ratio returns 0.0 when min commits is zero."""
        coupling = TemporalCoupling(
            file_a="a.py",
            file_b="b.py",
            co_change_count=0,
            commits_a=0,
            commits_b=0,
        )

        assert coupling.coupling_ratio == 0.0


class TestAnalyzeTemporalCoupling:
    """Tests for analyze_temporal_coupling."""

    def test_detects_two_files_changing_together(self):
        """Detects coupling when two files appear in same commits."""
        history = [
            make_commit(["a.py", "b.py"]),
            make_commit(["a.py", "b.py"]),
        ]

        result = _pairs(history, min_ratio=0.0)

        assert len(result) == 1
        coupling = result[0]
        assert coupling.file_a == "a.py"
        assert coupling.file_b == "b.py"
        assert coupling.co_change_count == 2
        assert coupling.commits_a == 2
        assert coupling.commits_b == 2
        assert coupling.coupling_ratio == 1.0

    def test_includes_pairs_above_threshold(self):
        """Includes pairs at or above the minimum ratio threshold."""
        # a.py: 2 commits, b.py: 4 commits, co-changes: 1
        # coupling_ratio = 1 / min(2, 4) = 0.5
        history = [
            make_commit(["a.py", "b.py"]),
            make_commit(["a.py"]),
            make_commit(["b.py"]),
            make_commit(["b.py"]),
            make_commit(["b.py"]),
        ]

        result = _pairs(history, min_ratio=0.5)
        assert len(result) == 1

    def test_excludes_pairs_below_threshold(self):
        """Excludes pairs below the minimum ratio threshold."""
        # a.py: 2 commits, b.py: 4 commits, co-changes: 1
        # coupling_ratio = 1 / min(2, 4) = 0.5
        history = [
            make_commit(["a.py", "b.py"]),
            make_commit(["a.py"]),
            make_commit(["b.py"]),
            make_commit(["b.py"]),
            make_commit(["b.py"]),
        ]

        result = _pairs(history, min_ratio=0.6)
        assert len(result) == 0

    def test_alphabetical_ordering_avoids_duplicates(self):
        """Files are ordered alphabetically so (b, a) becomes (a, b)."""
        history = [make_commit(["zebra.py", "apple.py"])]

        result = _pairs(history, min_ratio=0.0)

        assert len(result) == 1
        assert result[0].file_a == "apple.py"
        assert result[0].file_b == "zebra.py"

    def test_single_file_commits_produce_no_pairs(self):
        """Commits with only one file don't create any pairs."""
        history = [make_commit(["a.py"]), make_commit(["b.py"])]

        result = _pairs(history, min_ratio=0.0)

        assert len(result) == 0

    def test_empty_data_returns_empty_list(self):
        """Empty history returns empty list."""
        assert _pairs([]) == []

    def test_directional_rates_divide_by_each_side(self):
        history = [
            *[make_commit(["hub.py", "leaf.py"]) for _ in range(3)],
            *[make_commit(["hub.py"]) for _ in range(27)],
        ]

        [pair] = _pairs(history)

        assert (pair.file_a, pair.rate_a_to_b) == ("hub.py", 0.1)
        assert (pair.file_b, pair.rate_b_to_a) == ("leaf.py", 1.0)
        assert pair.coupling_ratio == 1.0
        assert pair.model_dump()["rate_a_to_b"] == 0.1

    def test_pairs_with_a_side_missing_from_live_paths_are_dropped_and_counted(self):
        history = [make_commit(["a.py", "b.py", "gone.py"]) for _ in range(2)]

        analysis = analyze_temporal_coupling(
            history,
            CouplingPolicy(),
            live_paths=frozenset({"a.py", "b.py"}),
        )

        assert [(pair.file_a, pair.file_b) for pair in analysis.couplings] == [("a.py", "b.py")]
        assert analysis.dropped_deleted_partners == 2

    def test_repeated_evidence_ranks_ahead_of_a_perfect_one_off(self):
        history = [
            *[make_commit(["src/a.py", "tests/test_a.py"]) for _ in range(11)],
            *[make_commit(["src/a.py"]) for _ in range(2)],
            *[make_commit(["tests/test_a.py"]) for _ in range(2)],
            make_commit(["src/one.py", "tests/test_one.py"]),
        ]

        result = _pairs(history)

        assert (result[0].file_a, result[0].file_b) == (
            "src/a.py",
            "tests/test_a.py",
        )
        assert result[0].confidence_lower_bound > result[-1].confidence_lower_bound

    def test_support_floor_excludes_one_off_pairs(self):
        history = [
            make_commit(["src/one.py", "tests/test_one.py"]),
            make_commit(["src/repeated.py", "tests/test_repeated.py"]),
            make_commit(["src/repeated.py", "tests/test_repeated.py"]),
        ]

        result = _pairs(history, min_shared_revisions=2)

        assert [(pair.file_a, pair.file_b) for pair in result] == [
            ("src/repeated.py", "tests/test_repeated.py")
        ]


class TestExcludeBulk:
    def test_commit_over_the_cap_is_bulk_and_counted(self):
        bulk = make_commit([f"generated/{i}.py" for i in range(51)])
        normal = make_commit(["a.py", "b.py"])

        kept, excluded = exclude_bulk([bulk, normal], max_changeset_size=50)

        assert bulk.is_bulk(50) and not normal.is_bulk(50)
        assert (kept, excluded) == ([normal], 1)

    def test_commit_at_the_cap_is_not_bulk(self):
        assert not make_commit([f"f{i}.py" for i in range(50)]).is_bulk(50)

    def test_bulk_commits_do_not_count_as_file_revisions(self):
        bulk_files = ["a.py", "b.py", *[f"generated/{i}.py" for i in range(49)]]
        history, _ = exclude_bulk(
            [make_commit(bulk_files), *[make_commit(["a.py", "b.py"]) for _ in range(2)]],
            max_changeset_size=50,
        )

        [pair] = _pairs(history)

        assert (pair.co_change_count, pair.commits_a, pair.commits_b) == (2, 2, 2)
