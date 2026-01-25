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
        gmap_data = {
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

        result = detect_temporal_coupling(gmap_data, min_ratio=0.0)

        assert len(result) == 1
        coupling = result[0]
        assert coupling.file_a == "a.py"
        assert coupling.file_b == "b.py"
        assert coupling.co_change_count == 2
        assert coupling.commits_a == 2
        assert coupling.commits_b == 2
        assert coupling.coupling_ratio == 1.0

    def test_filters_by_min_ratio_threshold(self):
        """Excludes pairs below the minimum ratio threshold."""
        gmap_data = {
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
                    ],
                },
                {
                    "timestamp": "2025-01-03T10:00:00Z",
                    "files": [
                        {"path": "a.py", "added_lines": 2, "deleted_lines": 0},
                    ],
                },
                {
                    "timestamp": "2025-01-04T10:00:00Z",
                    "files": [
                        {"path": "a.py", "added_lines": 1, "deleted_lines": 0},
                    ],
                },
            ]
        }
        # a.py: 4 commits, b.py: 1 commit, co-changes: 1
        # coupling_ratio = 1 / min(4, 1) = 1/1 = 1.0

        # With high threshold, should still include
        result_high = detect_temporal_coupling(gmap_data, min_ratio=0.9)
        assert len(result_high) == 1

        # Create data with lower coupling
        gmap_data_low = {
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
                    ],
                },
                {
                    "timestamp": "2025-01-03T10:00:00Z",
                    "files": [
                        {"path": "b.py", "added_lines": 2, "deleted_lines": 0},
                    ],
                },
                {
                    "timestamp": "2025-01-04T10:00:00Z",
                    "files": [
                        {"path": "b.py", "added_lines": 1, "deleted_lines": 0},
                    ],
                },
                {
                    "timestamp": "2025-01-05T10:00:00Z",
                    "files": [
                        {"path": "b.py", "added_lines": 1, "deleted_lines": 0},
                    ],
                },
            ]
        }
        # a.py: 2 commits, b.py: 4 commits, co-changes: 1
        # coupling_ratio = 1 / min(2, 4) = 1/2 = 0.5

        result_filtered = detect_temporal_coupling(gmap_data_low, min_ratio=0.6)
        assert len(result_filtered) == 0

        result_included = detect_temporal_coupling(gmap_data_low, min_ratio=0.5)
        assert len(result_included) == 1

    def test_alphabetical_ordering_avoids_duplicates(self):
        """Files are ordered alphabetically so (b, a) becomes (a, b)."""
        gmap_data = {
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

        result = detect_temporal_coupling(gmap_data, min_ratio=0.0)

        assert len(result) == 1
        assert result[0].file_a == "apple.py"
        assert result[0].file_b == "zebra.py"

    def test_single_file_commits_produce_no_pairs(self):
        """Commits with only one file don't create any pairs."""
        gmap_data = {
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

        result = detect_temporal_coupling(gmap_data, min_ratio=0.0)

        assert len(result) == 0

    def test_empty_data_returns_empty_list(self):
        """Empty gmap data returns empty list."""
        result = detect_temporal_coupling({}, min_ratio=0.0)
        assert result == []

        result = detect_temporal_coupling({"entries": []}, min_ratio=0.0)
        assert result == []
