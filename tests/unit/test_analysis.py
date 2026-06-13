"""Unit tests for repository analysis."""

import json
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from black_box_unlock.analysis import (
    _fetch_ci_failures,
    export_to_json,
    run_analysis,
)
from black_box_unlock.core.models import (
    AnalysisResult,
    AnalysisSummary,
    CouplingInfo,
    FileForensics,
)
from tests.factories import make_commit


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

    def test_hotspot_score_is_commits_times_complexity(self):
        """hotspot_score is commits × complexity (Tornhill's formula)."""
        forensics = FileForensics(
            path="src/auth.py",
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
        """Returns AnalysisResult with forensics from git history."""
        history = [
            make_commit(
                author_email="alice@example.com",
                files=[
                    {"path": "src/auth.py", "added_lines": 100, "deleted_lines": 20},
                    {"path": "src/user.py", "added_lines": 50, "deleted_lines": 10},
                ],
            ),
            make_commit(
                author_email="bob@example.com",
                files=[{"path": "src/auth.py", "added_lines": 30, "deleted_lines": 5}],
            ),
        ]

        with patch("black_box_unlock.analysis.fetch_git_history") as mock_fetch:
            mock_fetch.return_value = history
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
        history = [make_commit(["low.py", "high.py"], author_email="alice@example.com")]
        complexity_by_path = {"low.py": 1.0, "high.py": 50.0}

        with patch("black_box_unlock.analysis.fetch_git_history") as mock_fetch:
            mock_fetch.return_value = history
            with patch("black_box_unlock.analysis.indentation_complexity") as mock_cx:
                mock_cx.side_effect = lambda p: complexity_by_path.get(p.name, 0.0)
                result = run_analysis(Path("/fake/repo"), days=30)

        assert result.files[0].path == "high.py"
        assert result.files[1].path == "low.py"

    def test_includes_coupling_info(self):
        """Files include coupling info when above threshold."""
        history = [
            make_commit(["a.py", "b.py"], author_email="alice@example.com"),
            make_commit(["a.py", "b.py"], author_email="alice@example.com"),
        ]

        with patch("black_box_unlock.analysis.fetch_git_history") as mock_fetch:
            mock_fetch.return_value = history
            result = run_analysis(Path("/fake/repo"), days=30, min_coupling=0.3)

        # a.py and b.py have 100% coupling (2/2 commits together)
        a_file = next(f for f in result.files if f.path == "a.py")
        assert len(a_file.coupled_with) == 1
        assert a_file.coupled_with[0].file == "b.py"
        assert a_file.coupled_with[0].ratio == 1.0

    def test_summary_counts_high_risk_files(self):
        """Summary counts files with >3 authors as high risk."""
        history = [
            make_commit(["risky.py"], author_email="a@x.com"),
            make_commit(["risky.py"], author_email="b@x.com"),
            make_commit(["risky.py"], author_email="c@x.com"),
            make_commit(["risky.py"], author_email="d@x.com"),
            make_commit(["safe.py"], author_email="a@x.com"),
        ]

        with patch("black_box_unlock.analysis.fetch_git_history") as mock_fetch:
            mock_fetch.return_value = history
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
                    complexity=200.0,
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
        assert parsed["files"][0]["hotspot_score"] == 2000  # 10 commits * 200.0 complexity
        assert parsed["files"][0]["author_count"] == 4
        assert parsed["files"][0]["is_high_risk"] is True


class TestRunAnalysisWithCIData:
    """Tests for CI data integration in analysis."""

    @patch("black_box_unlock.analysis._fetch_ci_failures")
    @patch("black_box_unlock.analysis.fetch_git_history")
    def test_includes_build_failures_in_file_forensics(self, mock_history, mock_ci):
        """File forensics includes build_failures from CI data."""
        mock_history.return_value = [
            make_commit(
                author_email="test@example.com",
                files=[{"path": "src/main.py", "added_lines": 10, "deleted_lines": 5}],
            )
        ]
        mock_ci.return_value = {"src/main.py": 2}

        result = run_analysis(Path("/fake/repo"), days=30, include_ci=True)

        main_file = next(f for f in result.files if f.path == "src/main.py")
        assert main_file.build_failures == 2

    @patch("black_box_unlock.analysis._fetch_ci_failures")
    @patch("black_box_unlock.analysis.fetch_git_history")
    def test_defaults_build_failures_to_zero_when_file_not_in_ci_data(self, mock_history, mock_ci):
        """Files not in CI data get build_failures=0."""
        mock_history.return_value = [
            make_commit(
                author_email="test@example.com",
                files=[{"path": "src/main.py", "added_lines": 10, "deleted_lines": 5}],
            )
        ]
        mock_ci.return_value = {"src/other.py": 3}  # Different file

        result = run_analysis(Path("/fake/repo"), days=30, include_ci=True)

        main_file = next(f for f in result.files if f.path == "src/main.py")
        assert main_file.build_failures == 0

    @patch("black_box_unlock.analysis._fetch_ci_failures")
    @patch("black_box_unlock.analysis.fetch_git_history")
    def test_skips_ci_fetch_when_include_ci_is_false(self, mock_history, mock_ci):
        """Does not call _fetch_ci_failures when include_ci=False."""
        mock_history.return_value = [
            make_commit(
                author_email="test@example.com",
                files=[{"path": "src/main.py", "added_lines": 10, "deleted_lines": 5}],
            )
        ]

        run_analysis(Path("/fake/repo"), days=30, include_ci=False)

        mock_ci.assert_not_called()

    @patch("black_box_unlock.analysis._fetch_ci_failures")
    @patch("black_box_unlock.analysis.fetch_git_history")
    def test_include_ci_defaults_to_true(self, mock_history, mock_ci):
        """include_ci parameter defaults to True."""
        mock_history.return_value = [
            make_commit(
                author_email="test@example.com",
                files=[{"path": "src/main.py", "added_lines": 10, "deleted_lines": 5}],
            )
        ]
        mock_ci.return_value = {}

        run_analysis(Path("/fake/repo"), days=30)

        mock_ci.assert_called_once()

    def test_includes_bugfix_commit_counts(self):
        """File forensics include bugfix_commits from commit messages."""
        history = [
            make_commit(
                author_email="a@x.com",
                message="fix: crash on empty input",
                files=[{"path": "src/auth.py", "added_lines": 5, "deleted_lines": 1}],
            )
        ]

        with patch("black_box_unlock.analysis.fetch_git_history") as mock_fetch:
            mock_fetch.return_value = history
            result = run_analysis(Path("/fake/repo"), days=30)

        auth = next(f for f in result.files if f.path == "src/auth.py")
        assert auth.bugfix_commits == 1


class TestFlakyStepsInPipeline:
    @patch("black_box_unlock.analysis.detect_flaky_steps")
    @patch("black_box_unlock.analysis._fetch_ci_failures")
    @patch("black_box_unlock.analysis.fetch_git_history")
    def test_populates_flaky_steps(self, mock_hist, mock_ci, mock_flaky):
        from datetime import datetime

        from black_box_unlock.cicd.models import FlakyStep

        mock_hist.return_value = []
        mock_ci.return_value = {}
        mock_flaky.return_value = [
            FlakyStep(
                job_name="test (3.11)",
                step_name="Run tests",
                first_seen=datetime(2026, 6, 1),
                last_seen=datetime(2026, 6, 2),
                total_attempts=2,
                failures=1,
                flaky_count=1,
            )
        ]

        result = run_analysis(Path("/fake/repo"), days=30, include_ci=True)

        assert len(result.flaky_steps) == 1
        assert result.flaky_steps[0].step_name == "Run tests"

    @patch("black_box_unlock.analysis.detect_flaky_steps")
    @patch("black_box_unlock.analysis.fetch_git_history")
    def test_no_ci_skips_flaky_fetch(self, mock_hist, mock_flaky):
        mock_hist.return_value = []

        run_analysis(Path("/fake/repo"), days=30, include_ci=False)

        mock_flaky.assert_not_called()

    @patch("black_box_unlock.analysis.detect_flaky_steps")
    @patch("black_box_unlock.analysis._fetch_ci_failures")
    @patch("black_box_unlock.analysis.fetch_git_history")
    def test_flaky_fetch_failure_degrades_gracefully(self, mock_hist, mock_ci, mock_flaky):
        mock_hist.return_value = []
        mock_ci.return_value = {}
        mock_flaky.side_effect = Exception("gh not authenticated")

        result = run_analysis(Path("/fake/repo"), days=30, include_ci=True)

        assert result.flaky_steps == []

    @patch("black_box_unlock.analysis.detect_flaky_steps")
    @patch("black_box_unlock.analysis._fetch_ci_failures")
    @patch("black_box_unlock.analysis.fetch_git_history")
    def test_merges_duplicate_steps_across_runs(self, mock_hist, mock_ci, mock_flaky):
        """The same (job, step) flaky in two different runs becomes one summary."""
        from datetime import datetime

        from black_box_unlock.cicd.models import FlakyStep

        mock_hist.return_value = []
        mock_ci.return_value = {}
        mock_flaky.return_value = [
            FlakyStep(
                job_name="test (3.11)",
                step_name="Run tests",
                first_seen=datetime(2026, 6, 1),
                last_seen=datetime(2026, 6, 2),
                total_attempts=2,
                failures=1,
                flaky_count=1,
            ),
            FlakyStep(
                job_name="test (3.11)",
                step_name="Run tests",
                first_seen=datetime(2026, 6, 3),
                last_seen=datetime(2026, 6, 4),
                total_attempts=3,
                failures=2,
                flaky_count=2,
            ),
        ]

        result = run_analysis(Path("/fake/repo"), days=30, include_ci=True)

        assert len(result.flaky_steps) == 1
        merged = result.flaky_steps[0]
        assert merged.total_attempts == 5
        assert merged.failures == 3
        assert merged.flaky_count == 3
        assert merged.first_seen == datetime(2026, 6, 1)
        assert merged.last_seen == datetime(2026, 6, 4)


class TestFetchCIFailures:
    """Tests for _fetch_ci_failures helper."""

    @patch("black_box_unlock.analysis.fetch_workflow_runs")
    def test_returns_empty_dict_on_exception(self, mock_fetch):
        """Returns empty dict when CI fetch fails."""
        mock_fetch.side_effect = Exception("GitHub API unavailable")

        result = _fetch_ci_failures(Path("."))

        assert result == {}


class TestAutoXray:
    def _history(self):
        return [
            make_commit(
                author_email="a@x.com",
                files=[{"path": "mod.py", "added_lines": 5, "deleted_lines": 0}],
            )
        ]

    def test_top_files_get_functions(self, tmp_path):
        from black_box_unlock.core.models import FileXRay, FunctionChurn

        (tmp_path / "mod.py").write_text("def f():\n    return 1\n")
        fake = FileXRay(
            path="mod.py",
            days=30,
            revisions_analyzed=1,
            revision_cap_hit=False,
            functions=[FunctionChurn(name="f", revisions=1, lines_added=5, lines_deleted=0)],
        )
        with patch("black_box_unlock.analysis.fetch_git_history") as mock_hist:
            mock_hist.return_value = self._history()
            with patch("black_box_unlock.analysis.xray_file") as mock_xray:
                mock_xray.return_value = fake
                result = run_analysis(tmp_path, days=30, include_ci=False, xray_top=1)
        assert result.files[0].functions[0].name == "f"
        assert result.summary.xrayed_files == 1

    def test_xray_top_zero_disables(self, tmp_path):
        (tmp_path / "mod.py").write_text("def f():\n    return 1\n")
        with patch("black_box_unlock.analysis.fetch_git_history") as mock_hist:
            mock_hist.return_value = self._history()
            with patch("black_box_unlock.analysis.xray_file") as mock_xray:
                result = run_analysis(tmp_path, days=30, include_ci=False, xray_top=0)
        mock_xray.assert_not_called()
        assert result.summary.xrayed_files == 0

    def test_xray_failure_degrades_gracefully(self, tmp_path):
        (tmp_path / "mod.py").write_text("def f():\n    return 1\n")
        with patch("black_box_unlock.analysis.fetch_git_history") as mock_hist:
            mock_hist.return_value = self._history()
            with patch("black_box_unlock.analysis.xray_file") as mock_xray:
                mock_xray.side_effect = RuntimeError("boom")
                result = run_analysis(tmp_path, days=30, include_ci=False, xray_top=1)
        assert result.files[0].functions == []
        assert result.summary.xrayed_files == 0
