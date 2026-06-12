"""Unit tests for temporal coupling detection."""

from black_box_unlock.core.models import TemporalCoupling
from black_box_unlock.git.coupling import detect_temporal_coupling


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
        history = {
            "entries": [
                {
                    "timestamp": "2025-01-01T10:00:00Z",
                    "files": [
                        {"path": "a.py", "added_lines": 10, "deleted_lines": 0},
                        {"path": "b.py", "added_lines": 5, "deleted_lines": 0},
                    ],
                },
                {
                    "timestamp": "2025-01-02T10:00:00Z",
                    "files": [
                        {"path": "a.py", "added_lines": 3, "deleted_lines": 1},
                        {"path": "b.py", "added_lines": 2, "deleted_lines": 0},
                    ],
                },
            ]
        }

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
        history = {
            "entries": [
                {"files": [{"path": "a.py"}, {"path": "b.py"}]},
                {"files": [{"path": "a.py"}]},
                {"files": [{"path": "b.py"}]},
                {"files": [{"path": "b.py"}]},
                {"files": [{"path": "b.py"}]},
            ]
        }

        result = detect_temporal_coupling(history, min_ratio=0.5)
        assert len(result) == 1

    def test_excludes_pairs_below_threshold(self):
        """Excludes pairs below the minimum ratio threshold."""
        # a.py: 2 commits, b.py: 4 commits, co-changes: 1
        # coupling_ratio = 1 / min(2, 4) = 0.5
        history = {
            "entries": [
                {"files": [{"path": "a.py"}, {"path": "b.py"}]},
                {"files": [{"path": "a.py"}]},
                {"files": [{"path": "b.py"}]},
                {"files": [{"path": "b.py"}]},
                {"files": [{"path": "b.py"}]},
            ]
        }

        result = detect_temporal_coupling(history, min_ratio=0.6)
        assert len(result) == 0

    def test_alphabetical_ordering_avoids_duplicates(self):
        """Files are ordered alphabetically so (b, a) becomes (a, b)."""
        history = {
            "entries": [
                {
                    "timestamp": "2025-01-01T10:00:00Z",
                    "files": [
                        {"path": "zebra.py", "added_lines": 10, "deleted_lines": 0},
                        {"path": "apple.py", "added_lines": 5, "deleted_lines": 0},
                    ],
                },
            ]
        }

        result = detect_temporal_coupling(history, min_ratio=0.0)

        assert len(result) == 1
        assert result[0].file_a == "apple.py"
        assert result[0].file_b == "zebra.py"

    def test_single_file_commits_produce_no_pairs(self):
        """Commits with only one file don't create any pairs."""
        history = {
            "entries": [
                {
                    "timestamp": "2025-01-01T10:00:00Z",
                    "files": [
                        {"path": "a.py", "added_lines": 10, "deleted_lines": 0},
                    ],
                },
                {
                    "timestamp": "2025-01-02T10:00:00Z",
                    "files": [
                        {"path": "b.py", "added_lines": 5, "deleted_lines": 0},
                    ],
                },
            ]
        }

        result = detect_temporal_coupling(history, min_ratio=0.0)

        assert len(result) == 0

    def test_empty_data_returns_empty_list(self):
        """Empty history returns empty list."""
        result = detect_temporal_coupling({}, min_ratio=0.0)
        assert result == []

        result = detect_temporal_coupling({"entries": []}, min_ratio=0.0)
        assert result == []
