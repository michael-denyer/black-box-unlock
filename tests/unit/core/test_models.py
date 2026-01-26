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
