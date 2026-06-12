"""Tests for core data models."""

from datetime import datetime

import pytest

from black_box_unlock.core.models import FileChurn, FileForensics


class TestFileChurn:
    """Tests for FileChurn model."""

    def test_creates_valid_file_churn(self):
        """FileChurn accepts valid data."""
        churn = FileChurn(
            path="src/main.py",
            commits=10,
            lines_added=100,
            lines_deleted=50,
            first_commit=datetime(2025, 1, 1),
            last_commit=datetime(2025, 1, 25),
        )

        assert churn.path == "src/main.py"
        assert churn.commits == 10
        assert churn.lines_added == 100
        assert churn.lines_deleted == 50

    def test_total_lines_changed(self):
        """total_lines_changed returns sum of added and deleted."""
        churn = FileChurn(
            path="src/main.py",
            commits=5,
            lines_added=100,
            lines_deleted=30,
            first_commit=datetime(2025, 1, 1),
            last_commit=datetime(2025, 1, 25),
        )

        assert churn.total_lines_changed == 130

    def test_rejects_negative_commits(self):
        """FileChurn rejects negative commit count."""
        with pytest.raises(ValueError):
            FileChurn(
                path="src/main.py",
                commits=-1,
                lines_added=100,
                lines_deleted=50,
                first_commit=datetime(2025, 1, 1),
                last_commit=datetime(2025, 1, 25),
            )

    def test_rejects_empty_path(self):
        """FileChurn rejects empty path."""
        with pytest.raises(ValueError):
            FileChurn(
                path="",
                commits=10,
                lines_added=100,
                lines_deleted=50,
                first_commit=datetime(2025, 1, 1),
                last_commit=datetime(2025, 1, 25),
            )


class TestFileForensicsBuildFailures:
    """Tests for build_failures field in FileForensics."""

    def test_build_failures_defaults_to_zero(self):
        """build_failures defaults to 0."""
        forensics = FileForensics(
            path="src/main.py",
            commits=5,
            lines_changed=100,
            authors=["alice"],
            coupled_with=[],
        )
        assert forensics.build_failures == 0

    def test_build_failures_can_be_set(self):
        """build_failures can be set to a value."""
        forensics = FileForensics(
            path="src/main.py",
            commits=5,
            lines_changed=100,
            authors=["alice"],
            coupled_with=[],
            build_failures=3,
        )
        assert forensics.build_failures == 3

    def test_rejects_negative_build_failures(self):
        """build_failures rejects negative values."""
        with pytest.raises(ValueError):
            FileForensics(
                path="src/main.py",
                commits=5,
                lines_changed=100,
                authors=["alice"],
                coupled_with=[],
                build_failures=-1,
            )


class TestFunctionChurn:
    def test_hotspot_score_is_revisions_times_complexity(self):
        from black_box_unlock.core.models import FunctionChurn

        f = FunctionChurn(
            name="f",
            start_line=1,
            end_line=5,
            revisions=3,
            lines_added=10,
            lines_deleted=2,
            complexity=4.0,
        )
        assert f.hotspot_score == 12.0

    def test_header_only_defaults(self):
        from black_box_unlock.core.models import FunctionChurn

        f = FunctionChurn(name="parse", revisions=2, lines_added=5, lines_deleted=1)
        assert f.start_line == 0 and f.end_line == 0
        assert f.complexity == 0.0 and f.hotspot_score == 0.0


class TestFileXRay:
    def test_serializes_with_computed_score(self):
        from black_box_unlock.core.models import FileXRay, FunctionChurn

        xr = FileXRay(
            path="a.py",
            days=365,
            revisions_analyzed=4,
            revision_cap_hit=False,
            functions=[FunctionChurn(name="f", revisions=1, lines_added=1, lines_deleted=0)],
        )
        dumped = xr.model_dump(mode="json")
        assert dumped["functions"][0]["hotspot_score"] == 0.0


class TestFileForensicsFunctions:
    def test_functions_default_empty(self):
        from black_box_unlock.core.models import FileForensics

        f = FileForensics(path="a.py", commits=1, lines_changed=1, authors=[], coupled_with=[])
        assert f.functions == []


class TestFunctionCoupling:
    def test_ratio_uses_min_revisions(self):
        from black_box_unlock.core.models import FunctionCoupling

        c = FunctionCoupling(
            function_a="alpha",
            function_b="beta",
            shared_revisions=3,
            revisions_a=4,
            revisions_b=6,
        )
        assert c.coupling_ratio == 0.75

    def test_zero_min_revisions_gives_zero_ratio(self):
        from black_box_unlock.core.models import FunctionCoupling

        c = FunctionCoupling(
            function_a="a", function_b="b", shared_revisions=0, revisions_a=0, revisions_b=5
        )
        assert c.coupling_ratio == 0.0

    def test_filexray_coupling_defaults_empty(self):
        from black_box_unlock.core.models import FileXRay

        xr = FileXRay(
            path="a.py", days=365, revisions_analyzed=1, revision_cap_hit=False, functions=[]
        )
        assert xr.coupling == []
