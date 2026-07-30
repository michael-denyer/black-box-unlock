"""Unit tests for temporal coupling detection."""

from black_box_unlock.core.models import TemporalCoupling
from black_box_unlock.git.coupling import analyze_temporal_coupling, detect_temporal_coupling
from tests.factories import make_commit


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


class TestDetectTemporalCoupling:
    """Tests for detect_temporal_coupling function."""

    def test_detects_two_files_changing_together(self):
        """Detects coupling when two files appear in same commits."""
        history = [
            make_commit(["a.py", "b.py"]),
            make_commit(["a.py", "b.py"]),
        ]

        result = detect_temporal_coupling(history, min_ratio=0.0)

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

        result = detect_temporal_coupling(history, min_ratio=0.5)
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

        result = detect_temporal_coupling(history, min_ratio=0.6)
        assert len(result) == 0

    def test_alphabetical_ordering_avoids_duplicates(self):
        """Files are ordered alphabetically so (b, a) becomes (a, b)."""
        history = [make_commit(["zebra.py", "apple.py"])]

        result = detect_temporal_coupling(history, min_ratio=0.0)

        assert len(result) == 1
        assert result[0].file_a == "apple.py"
        assert result[0].file_b == "zebra.py"

    def test_single_file_commits_produce_no_pairs(self):
        """Commits with only one file don't create any pairs."""
        history = [make_commit(["a.py"]), make_commit(["b.py"])]

        result = detect_temporal_coupling(history, min_ratio=0.0)

        assert len(result) == 0

    def test_empty_data_returns_empty_list(self):
        """Empty history returns empty list."""
        assert detect_temporal_coupling([], min_ratio=0.0) == []

    def test_bulk_changeset_does_not_create_coupling_pairs(self):
        history = [make_commit([f"generated/{i}.py" for i in range(51)])]

        assert detect_temporal_coupling(history, min_ratio=0.0) == []

    def test_bulk_changes_still_count_as_file_revisions(self):
        bulk_files = ["a.py", "b.py", *[f"generated/{i}.py" for i in range(49)]]
        history = [
            make_commit(bulk_files),
            make_commit(["a.py", "b.py"]),
        ]

        result = detect_temporal_coupling(history, min_ratio=0.5)

        assert len(result) == 1
        assert result[0].co_change_count == 1
        assert result[0].commits_a == 2
        assert result[0].commits_b == 2
        assert result[0].coupling_ratio == 0.5

    def test_repeated_evidence_ranks_ahead_of_a_perfect_one_off(self):
        history = [
            *[make_commit(["src/a.py", "tests/test_a.py"]) for _ in range(11)],
            *[make_commit(["src/a.py"]) for _ in range(2)],
            *[make_commit(["tests/test_a.py"]) for _ in range(2)],
            make_commit(["src/one.py", "tests/test_one.py"]),
        ]

        result = analyze_temporal_coupling(history, min_ratio=0.0).couplings

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

        result = analyze_temporal_coupling(
            history,
            min_ratio=0.0,
            min_shared_revisions=2,
        ).couplings

        assert [(pair.file_a, pair.file_b) for pair in result] == [
            ("src/repeated.py", "tests/test_repeated.py")
        ]
