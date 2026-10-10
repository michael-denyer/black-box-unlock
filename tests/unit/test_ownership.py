"""Unit tests for file ownership calculation."""

from datetime import datetime, timezone

import pytest

from black_box_unlock.core.models import FileOwnership
from black_box_unlock.git.ownership import (
    OwnershipRisk,
    ownership_risk,
    parse_ownership_from_history,
)
from tests.factories import make_commit


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
        """is_high_risk is True when file has >3 authors and no author holds half."""
        ownership = FileOwnership(
            path="src/auth.py",
            authors=["a@x.com", "b@x.com", "c@x.com", "d@x.com"],
            commits=20,
            main_author_share=0.25,
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


class TestParseOwnershipFromHistory:
    """Tests for parse_ownership_from_history function."""

    def test_calculates_ownership_from_history(self):
        """Calculates file ownership from git history entries."""
        history = [
            make_commit(["a.py", "b.py"], author_email="alice@example.com"),
            make_commit(["a.py"], author_email="bob@example.com"),
        ]

        result = parse_ownership_from_history(history)

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
        assert parse_ownership_from_history([]) == []

    def test_same_author_multiple_commits_counted_once(self):
        """Same author across multiple commits is counted once per file."""
        history = [
            make_commit(["a.py"], author_email="alice@example.com"),
            make_commit(["a.py"], author_email="alice@example.com"),
        ]

        result = parse_ownership_from_history(history)

        assert len(result) == 1
        assert result[0].author_count == 1
        assert result[0].commits == 2

    def test_missing_author_email_becomes_unknown(self):
        """Missing or empty author_email is recorded as 'unknown'."""
        history = [
            make_commit(["a.py"], author_email=""),
            make_commit(["b.py"], author_email=""),
        ]

        result = parse_ownership_from_history(history)

        assert len(result) == 2
        a_ownership = next(o for o in result if o.path == "a.py")
        b_ownership = next(o for o in result if o.path == "b.py")

        assert a_ownership.authors == ["unknown"]
        assert b_ownership.authors == ["unknown"]


def _only(history):
    (ownership,) = parse_ownership_from_history(history)
    return ownership


def _commits(author: str, count: int, *, day: int = 1, path: str = "a.py"):
    return [
        make_commit([path], author_email=author, timestamp=f"2026-01-{day:02d}T00:00:00+00:00")
        for _ in range(count)
    ]


class TestMainAuthor:
    def test_dominant_author_among_four_has_a_ninety_percent_share(self):
        history = _commits("a@x.com", 9) + _commits("b@x.com", 1) + _commits("c@x.com", 0)
        ownership = _only(history)

        assert ownership.main_author == "a@x.com"
        assert ownership.main_author_share == pytest.approx(0.9)
        assert ownership.authors_by_commits == {"a@x.com": 9, "b@x.com": 1}

    def test_equal_authors_each_hold_a_third(self):
        history = _commits("a@x.com", 2) + _commits("b@x.com", 2) + _commits("c@x.com", 2)

        assert _only(history).main_author_share == pytest.approx(1 / 3)

    def test_tie_goes_to_the_most_recent_author(self):
        history = _commits("zed@x.com", 2, day=10) + _commits("amy@x.com", 2, day=5)

        assert _only(history).main_author == "zed@x.com"

    def test_tie_with_equal_recency_goes_to_the_lower_name(self):
        history = _commits("zed@x.com", 1, day=5) + _commits("amy@x.com", 1, day=5)

        assert _only(history).main_author == "amy@x.com"

    def test_bot_commits_count_in_commits_but_not_in_the_share(self):
        history = _commits("alice@x.com", 1) + _commits("dependabot[bot]@x.com", 3, day=20)
        ownership = _only(history)

        assert ownership.commits == 4
        assert ownership.main_author == "alice@x.com"
        assert ownership.main_author_share == 1.0

    def test_bot_only_file_has_no_owner_no_share_and_no_last_active(self):
        ownership = _only(_commits("dependabot[bot]@x.com", 2))

        assert ownership.main_author is None
        assert ownership.main_author_share == 0.0
        assert ownership.last_active is None
        assert ownership.authors_by_commits == {}


class TestLastActive:
    def test_is_the_latest_human_commit_and_ignores_later_bot_commits(self):
        history = (
            _commits("alice@x.com", 1, day=3)
            + _commits("bob@x.com", 1, day=7)
            + _commits("dependabot[bot]@x.com", 1, day=28)
        )

        assert _only(history).last_active.day == 7


class TestOwnershipRisk:
    @pytest.mark.parametrize(
        ("authors", "share", "expected"),
        [
            (3, 0.34, OwnershipRisk.owned),
            (1, 1.0, OwnershipRisk.owned),
            (0, 0.0, OwnershipRisk.owned),
            (4, 0.9, OwnershipRisk.shared),
            (4, 0.5, OwnershipRisk.shared),
            (4, 0.49, OwnershipRisk.diffuse),
            (6, 0.2, OwnershipRisk.diffuse),
        ],
    )
    def test_rules(self, authors, share, expected):
        ownership = FileOwnership(
            path="a.py",
            authors=[f"{i}@x.com" for i in range(authors)],
            commits=10,
            main_author_share=share,
        )

        assert ownership_risk(ownership) is expected

    def test_orphaned_is_never_returned(self):
        ownership = FileOwnership(
            path="a.py",
            authors=["a@x.com"],
            commits=1,
            main_author="a@x.com",
            main_author_share=1.0,
            last_active=datetime(2020, 1, 1, tzinfo=timezone.utc),
        )

        assert ownership_risk(ownership) is not OwnershipRisk.orphaned
