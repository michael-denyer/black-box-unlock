"""Unit tests for file ownership calculation."""

import pytest

from black_box_unlock.core.models import FileOwnership
from black_box_unlock.git.ownership import calculate_file_ownership, parse_ownership_from_history


class TestFileOwnershipModel:
    """Tests for FileOwnership data model."""

    def test_creates_ownership_with_required_fields(self):
        """Creates a FileOwnership with all required fields."""
        ownership = FileOwnership(
            path="src/auth.py",
            authors=["alice@example.com", "bob@example.com"],
            commits=10,
        )

        assert ownership.path == "src/auth.py"
        assert ownership.authors == ["alice@example.com", "bob@example.com"]
        assert ownership.commits == 10

    def test_author_count_returns_number_of_authors(self):
        """author_count returns the number of unique authors."""
        ownership = FileOwnership(
            path="src/auth.py",
            authors=["alice@example.com", "bob@example.com", "charlie@example.com"],
            commits=15,
        )

        assert ownership.author_count == 3

    def test_is_high_risk_true_when_more_than_three_authors(self):
        """is_high_risk is True when file has >3 authors."""
        ownership = FileOwnership(
            path="src/auth.py",
            authors=["a@x.com", "b@x.com", "c@x.com", "d@x.com"],
            commits=20,
        )

        assert ownership.is_high_risk is True

    def test_is_high_risk_false_when_three_or_fewer_authors(self):
        """is_high_risk is False when file has <=3 authors."""
        ownership = FileOwnership(
            path="src/auth.py",
            authors=["a@x.com", "b@x.com", "c@x.com"],
            commits=15,
        )

        assert ownership.is_high_risk is False

    def test_rejects_empty_path(self):
        """Rejects FileOwnership with empty path."""
        with pytest.raises(ValueError, match="path must not be empty"):
            FileOwnership(path="  ", authors=["a@x.com"], commits=1)

    def test_rejects_negative_commits(self):
        """Rejects FileOwnership with negative commits."""
        with pytest.raises(ValueError, match="commits must be non-negative"):
            FileOwnership(path="a.py", authors=["a@x.com"], commits=-1)


class TestCalculateFileOwnership:
    """Tests for calculate_file_ownership function."""

    def test_calculates_ownership_from_history(self):
        """Calculates file ownership from git history entries."""
        history = {
            "entries": [
                {
                    "author_email": "alice@example.com",
                    "files": [
                        {"path": "a.py", "added_lines": 10, "deleted_lines": 0},
                        {"path": "b.py", "added_lines": 5, "deleted_lines": 0},
                    ],
                },
                {
                    "author_email": "bob@example.com",
                    "files": [
                        {"path": "a.py", "added_lines": 3, "deleted_lines": 1},
                    ],
                },
            ]
        }

        result = calculate_file_ownership(history)

        assert len(result) == 2
        a_ownership = next(o for o in result if o.path == "a.py")
        b_ownership = next(o for o in result if o.path == "b.py")

        assert a_ownership.author_count == 2
        assert set(a_ownership.authors) == {"alice@example.com", "bob@example.com"}
        assert a_ownership.commits == 2

        assert b_ownership.author_count == 1
        assert b_ownership.authors == ["alice@example.com"]
        assert b_ownership.commits == 1

    def test_empty_data_returns_empty_list(self):
        """Empty history returns empty list."""
        assert calculate_file_ownership({}) == []
        assert calculate_file_ownership({"entries": []}) == []

    def test_same_author_multiple_commits_counted_once(self):
        """Same author across multiple commits is counted once per file."""
        history = {
            "entries": [
                {
                    "author_email": "alice@example.com",
                    "files": [{"path": "a.py", "added_lines": 10, "deleted_lines": 0}],
                },
                {
                    "author_email": "alice@example.com",
                    "files": [{"path": "a.py", "added_lines": 5, "deleted_lines": 2}],
                },
            ]
        }

        result = calculate_file_ownership(history)

        assert len(result) == 1
        assert result[0].author_count == 1
        assert result[0].commits == 2

    def test_missing_author_email_becomes_unknown(self):
        """Missing or empty author_email is recorded as 'unknown'."""
        history = {
            "entries": [
                {
                    "author_email": "",
                    "files": [{"path": "a.py", "added_lines": 10, "deleted_lines": 0}],
                },
                {
                    "files": [{"path": "b.py", "added_lines": 5, "deleted_lines": 0}],
                },
            ]
        }

        result = parse_ownership_from_history(history)

        assert len(result) == 2
        a_ownership = next(o for o in result if o.path == "a.py")
        b_ownership = next(o for o in result if o.path == "b.py")

        assert a_ownership.authors == ["unknown"]
        assert b_ownership.authors == ["unknown"]

    def test_calculate_file_ownership_is_aliased(self):
        """calculate_file_ownership is an alias for parse_ownership_from_history."""
        assert calculate_file_ownership is parse_ownership_from_history
