"""Unit tests for repository analysis."""

import json
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from black_box_unlock.analysis import export_to_json, run_analysis
from black_box_unlock.core.models import (
    AnalysisResult,
    AnalysisSummary,
    CouplingInfo,
    FileForensics,
)


class TestFileForensicsModel:
    """Tests for FileForensics data model."""

    def test_creates_file_forensics_with_required_fields(self):
        """Creates a FileForensics with all required fields."""
        forensics = FileForensics(
            path="src/auth.py",
            commits=42,
            lines_changed=1234,
            authors=["alice@example.com", "bob@example.com"],
            coupled_with=[],
        )

        assert forensics.path == "src/auth.py"
        assert forensics.commits == 42
        assert forensics.lines_changed == 1234
        assert forensics.authors == ["alice@example.com", "bob@example.com"]
        assert forensics.coupled_with == []

    def test_hotspot_score_is_commits_times_lines_changed(self):
        """hotspot_score is commits × lines_changed."""
        forensics = FileForensics(
            path="src/auth.py",
            commits=42,
            lines_changed=1234,
            authors=["alice@example.com"],
            coupled_with=[],
        )

        assert forensics.hotspot_score == 42 * 1234

    def test_author_count_returns_number_of_authors(self):
        """author_count returns len(authors)."""
        forensics = FileForensics(
            path="src/auth.py",
            commits=10,
            lines_changed=100,
            authors=["a@x.com", "b@x.com", "c@x.com"],
            coupled_with=[],
        )

        assert forensics.author_count == 3

    def test_is_high_risk_true_when_more_than_three_authors(self):
        """is_high_risk is True when author_count > 3."""
        forensics = FileForensics(
            path="src/auth.py",
            commits=10,
            lines_changed=100,
            authors=["a@x.com", "b@x.com", "c@x.com", "d@x.com"],
            coupled_with=[],
        )

        assert forensics.is_high_risk is True

    def test_is_high_risk_false_when_three_or_fewer_authors(self):
        """is_high_risk is False when author_count <= 3."""
        forensics = FileForensics(
            path="src/auth.py",
            commits=10,
            lines_changed=100,
            authors=["a@x.com", "b@x.com", "c@x.com"],
            coupled_with=[],
        )

        assert forensics.is_high_risk is False


class TestCouplingInfoModel:
    """Tests for CouplingInfo data model."""

    def test_creates_coupling_info(self):
        """Creates a CouplingInfo with file and ratio."""
        info = CouplingInfo(file="src/tokens.py", ratio=0.85)

        assert info.file == "src/tokens.py"
        assert info.ratio == 0.85


class TestAnalysisSummaryModel:
    """Tests for AnalysisSummary data model."""

    def test_creates_summary(self):
        """Creates an AnalysisSummary with counts."""
        summary = AnalysisSummary(
            total_files=142,
            high_risk_ownership=8,
            coupled_pairs=12,
        )

        assert summary.total_files == 142
        assert summary.high_risk_ownership == 8
        assert summary.coupled_pairs == 12


class TestAnalysisResultModel:
    """Tests for AnalysisResult data model."""

    def test_creates_analysis_result(self):
        """Creates an AnalysisResult with all fields."""
        now = datetime(2026, 1, 25, 15, 30, 0)
        result = AnalysisResult(
            repo="black-box-unlock",
            analyzed_days=30,
            generated_at=now,
            files=[
                FileForensics(
                    path="src/auth.py",
                    commits=42,
                    lines_changed=1234,
                    authors=["alice@example.com"],
                    coupled_with=[],
                )
            ],
            summary=AnalysisSummary(
                total_files=1,
                high_risk_ownership=0,
                coupled_pairs=0,
            ),
        )

        assert result.repo == "black-box-unlock"
        assert result.analyzed_days == 30
        assert result.generated_at == now
        assert len(result.files) == 1
        assert result.summary.total_files == 1


class TestRunAnalysis:
    """Tests for run_analysis function."""

    def test_returns_analysis_result_with_file_data(self):
        """Returns AnalysisResult with forensics from gmap data."""
        gmap_output = {
            "entries": [
                {
                    "timestamp": "2026-01-20T10:00:00Z",
                    "author_email": "alice@example.com",
                    "files": [
                        {"path": "src/auth.py", "added_lines": 100, "deleted_lines": 20},
                        {"path": "src/user.py", "added_lines": 50, "deleted_lines": 10},
                    ],
                },
                {
                    "timestamp": "2026-01-21T10:00:00Z",
                    "author_email": "bob@example.com",
                    "files": [
                        {"path": "src/auth.py", "added_lines": 30, "deleted_lines": 5},
                    ],
                },
            ]
        }

        with patch("black_box_unlock.analysis._fetch_gmap_data") as mock_fetch:
            mock_fetch.return_value = gmap_output
            result = run_analysis(Path("/fake/repo"), days=30)

        assert isinstance(result, AnalysisResult)
        assert result.analyzed_days == 30
        assert len(result.files) == 2

        # Check auth.py forensics
        auth_file = next(f for f in result.files if f.path == "src/auth.py")
        assert auth_file.commits == 2
        assert auth_file.lines_changed == 155  # 100+20+30+5
        assert auth_file.author_count == 2
        assert set(auth_file.authors) == {"alice@example.com", "bob@example.com"}

    def test_computes_hotspot_scores(self):
        """Files are sorted by hotspot_score descending."""
        gmap_output = {
            "entries": [
                {
                    "timestamp": "2026-01-20T10:00:00Z",
                    "author_email": "alice@example.com",
                    "files": [
                        {"path": "low.py", "added_lines": 10, "deleted_lines": 0},
                        {"path": "high.py", "added_lines": 1000, "deleted_lines": 0},
                    ],
                },
            ]
        }

        with patch("black_box_unlock.analysis._fetch_gmap_data") as mock_fetch:
            mock_fetch.return_value = gmap_output
            result = run_analysis(Path("/fake/repo"), days=30)

        # Should be sorted by hotspot_score descending
        assert result.files[0].path == "high.py"
        assert result.files[1].path == "low.py"

    def test_includes_coupling_info(self):
        """Files include coupling info when above threshold."""
        gmap_output = {
            "entries": [
                {
                    "timestamp": "2026-01-20T10:00:00Z",
                    "author_email": "alice@example.com",
                    "files": [
                        {"path": "a.py", "added_lines": 10, "deleted_lines": 0},
                        {"path": "b.py", "added_lines": 10, "deleted_lines": 0},
                    ],
                },
                {
                    "timestamp": "2026-01-21T10:00:00Z",
                    "author_email": "alice@example.com",
                    "files": [
                        {"path": "a.py", "added_lines": 10, "deleted_lines": 0},
                        {"path": "b.py", "added_lines": 10, "deleted_lines": 0},
                    ],
                },
            ]
        }

        with patch("black_box_unlock.analysis._fetch_gmap_data") as mock_fetch:
            mock_fetch.return_value = gmap_output
            result = run_analysis(Path("/fake/repo"), days=30, min_coupling=0.3)

        # a.py and b.py have 100% coupling (2/2 commits together)
        a_file = next(f for f in result.files if f.path == "a.py")
        assert len(a_file.coupled_with) == 1
        assert a_file.coupled_with[0].file == "b.py"
        assert a_file.coupled_with[0].ratio == 1.0

    def test_summary_counts_high_risk_files(self):
        """Summary counts files with >3 authors as high risk."""
        gmap_output = {
            "entries": [
                {
                    "timestamp": "2026-01-20T10:00:00Z",
                    "author_email": "a@x.com",
                    "files": [{"path": "risky.py", "added_lines": 10, "deleted_lines": 0}],
                },
                {
                    "timestamp": "2026-01-21T10:00:00Z",
                    "author_email": "b@x.com",
                    "files": [{"path": "risky.py", "added_lines": 10, "deleted_lines": 0}],
                },
                {
                    "timestamp": "2026-01-22T10:00:00Z",
                    "author_email": "c@x.com",
                    "files": [{"path": "risky.py", "added_lines": 10, "deleted_lines": 0}],
                },
                {
                    "timestamp": "2026-01-23T10:00:00Z",
                    "author_email": "d@x.com",
                    "files": [{"path": "risky.py", "added_lines": 10, "deleted_lines": 0}],
                },
                {
                    "timestamp": "2026-01-24T10:00:00Z",
                    "author_email": "a@x.com",
                    "files": [{"path": "safe.py", "added_lines": 10, "deleted_lines": 0}],
                },
            ]
        }

        with patch("black_box_unlock.analysis._fetch_gmap_data") as mock_fetch:
            mock_fetch.return_value = gmap_output
            result = run_analysis(Path("/fake/repo"), days=30)

        assert result.summary.high_risk_ownership == 1
        assert result.summary.total_files == 2


class TestExportToJson:
    """Tests for export_to_json function."""

    def test_exports_valid_json(self):
        """Exports AnalysisResult to valid JSON string."""
        now = datetime(2026, 1, 25, 15, 30, 0)
        result = AnalysisResult(
            repo="test-repo",
            analyzed_days=30,
            generated_at=now,
            files=[
                FileForensics(
                    path="src/auth.py",
                    commits=10,
                    lines_changed=200,
                    authors=["alice@example.com"],
                    coupled_with=[CouplingInfo(file="src/user.py", ratio=0.8)],
                )
            ],
            summary=AnalysisSummary(
                total_files=1,
                high_risk_ownership=0,
                coupled_pairs=1,
            ),
        )

        json_str = export_to_json(result)

        # Should be valid JSON
        parsed = json.loads(json_str)
        assert parsed["repo"] == "test-repo"
        assert parsed["analyzed_days"] == 30
        assert len(parsed["files"]) == 1
        assert parsed["files"][0]["path"] == "src/auth.py"
        assert parsed["files"][0]["coupled_with"][0]["file"] == "src/user.py"

    def test_includes_computed_properties(self):
        """JSON includes computed properties like hotspot_score."""
        now = datetime(2026, 1, 25, 15, 30, 0)
        result = AnalysisResult(
            repo="test-repo",
            analyzed_days=30,
            generated_at=now,
            files=[
                FileForensics(
                    path="src/auth.py",
                    commits=10,
                    lines_changed=200,
                    authors=["a@x.com", "b@x.com", "c@x.com", "d@x.com"],
                    coupled_with=[],
                )
            ],
            summary=AnalysisSummary(
                total_files=1,
                high_risk_ownership=1,
                coupled_pairs=0,
            ),
        )

        json_str = export_to_json(result)
        parsed = json.loads(json_str)

        # Computed properties should be in output
        assert parsed["files"][0]["hotspot_score"] == 2000  # 10 * 200
        assert parsed["files"][0]["author_count"] == 4
        assert parsed["files"][0]["is_high_risk"] is True
