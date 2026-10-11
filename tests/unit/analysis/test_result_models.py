"""Unit tests for the analysis result models."""

from datetime import datetime

from black_box_unlock.core.models import (
    AnalysisResult,
    AnalysisSummary,
    CouplingInfo,
    FileForensics,
)
from black_box_unlock.path_roles import PathRole
from tests.factories import make_provenance


class TestFileForensicsModel:
    """Tests for FileForensics data model."""

    def test_creates_file_forensics_with_required_fields(self):
        """Creates a FileForensics with all required fields."""
        forensics = FileForensics(
            path="src/auth.py",
            path_role=PathRole.source,
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

    def test_hotspot_score_is_commits_times_complexity(self):
        """hotspot_score is commits × complexity (Tornhill's formula)."""
        forensics = FileForensics(
            path="src/auth.py",
            path_role=PathRole.source,
            commits=42,
            lines_changed=1234,
            complexity=10.0,
            authors=["alice@example.com"],
            coupled_with=[],
        )

        assert forensics.hotspot_score == 420.0

    def test_author_count_returns_number_of_authors(self):
        """author_count returns len(authors)."""
        forensics = FileForensics(
            path="src/auth.py",
            path_role=PathRole.source,
            commits=10,
            lines_changed=100,
            authors=["a@x.com", "b@x.com", "c@x.com"],
            coupled_with=[],
        )

        assert forensics.author_count == 3

    def test_is_high_risk_true_when_more_than_three_authors(self):
        """is_high_risk is True when author_count > 3 and no author holds half."""
        forensics = FileForensics(
            path="src/auth.py",
            path_role=PathRole.source,
            commits=10,
            lines_changed=100,
            authors=["a@x.com", "b@x.com", "c@x.com", "d@x.com"],
            main_author_share=0.25,
            coupled_with=[],
        )

        assert forensics.is_high_risk is True

    def test_is_high_risk_false_when_three_or_fewer_authors(self):
        """is_high_risk is False when author_count <= 3."""
        forensics = FileForensics(
            path="src/auth.py",
            path_role=PathRole.source,
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
                    path_role=PathRole.source,
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
            provenance=make_provenance(),
        )

        assert result.repo == "black-box-unlock"
        assert result.analyzed_days == 30
        assert result.generated_at == now
        assert len(result.files) == 1
        assert result.summary.total_files == 1
