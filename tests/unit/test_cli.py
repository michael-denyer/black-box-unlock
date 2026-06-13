"""Unit tests for CLI commands."""

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from black_box_unlock.cli import app
from black_box_unlock.core.exceptions import InsufficientHistoryError
from black_box_unlock.validation import ValidationResult

runner = CliRunner()


def _validation_result(repo: str = "demo", spearman: float | None = 0.62) -> ValidationResult:
    return ValidationResult(
        repo=repo,
        days=730,
        split=0.5,
        cutoff=datetime(2025, 6, 12, tzinfo=timezone.utc),
        file_count=120,
        spearman=spearman,
        top_decile_share=0.45,
        bugfix_coverage=0.88,
        test_bugfix_touches=200,
    )


class TestAnalyzeRepoCommand:
    """Tests for analyze-repo command."""

    def test_outputs_json_format(self):
        """--output=json produces JSON to stdout."""
        mock_result = MagicMock()
        mock_result.repo = "test-repo"
        mock_result.analyzed_days = 30
        mock_result.files = []
        mock_result.summary.total_files = 0
        mock_result.summary.high_risk_ownership = 0
        mock_result.summary.coupled_pairs = 0

        with patch("black_box_unlock.cli.run_analysis") as mock_analysis:
            mock_analysis.return_value = mock_result
            with patch("black_box_unlock.cli.export_to_json") as mock_export:
                mock_export.return_value = '{"repo": "test-repo"}'
                result = runner.invoke(app, ["analyze-repo", "--output", "json"])

        assert result.exit_code == 0
        assert '{"repo": "test-repo"}' in result.stdout

    def test_outputs_html_format(self):
        """--output=html produces HTML to stdout."""
        mock_result = MagicMock()
        mock_result.repo = "test-repo"

        with patch("black_box_unlock.cli.run_analysis") as mock_analysis:
            mock_analysis.return_value = mock_result
            with patch("black_box_unlock.cli.generate_html_report") as mock_html:
                mock_html.return_value = "<!DOCTYPE html><html></html>"
                result = runner.invoke(app, ["analyze-repo", "--output", "html"])

        assert result.exit_code == 0
        assert "<!DOCTYPE html>" in result.stdout

    def test_uses_days_option(self):
        """--days option is passed to run_analysis."""
        mock_result = MagicMock()
        mock_result.files = []
        mock_result.summary.total_files = 0

        with patch("black_box_unlock.cli.run_analysis") as mock_analysis:
            mock_analysis.return_value = mock_result
            with patch("black_box_unlock.cli.export_to_json") as mock_export:
                mock_export.return_value = "{}"
                runner.invoke(app, ["analyze-repo", "--days", "60", "--output", "json"])

        mock_analysis.assert_called_once()
        _, kwargs = mock_analysis.call_args
        assert kwargs.get("days") == 60

    def test_defaults_to_current_directory(self):
        """Uses current directory when no path specified."""
        mock_result = MagicMock()
        mock_result.files = []

        with patch("black_box_unlock.cli.run_analysis") as mock_analysis:
            mock_analysis.return_value = mock_result
            with patch("black_box_unlock.cli.export_to_json") as mock_export:
                mock_export.return_value = "{}"
                runner.invoke(app, ["analyze-repo", "--output", "json"])

        mock_analysis.assert_called_once()
        call_args = mock_analysis.call_args
        # First positional arg is repo_path
        assert call_args[0][0] == Path(".")

    def test_no_ci_flag_skips_ci_analysis(self):
        """--no-ci flag passes include_ci=False to run_analysis."""
        mock_result = MagicMock()
        mock_result.files = []

        with patch("black_box_unlock.cli.run_analysis") as mock_run_analysis:
            mock_run_analysis.return_value = mock_result
            with patch("black_box_unlock.cli.export_to_json") as mock_export:
                mock_export.return_value = "{}"
                result = runner.invoke(app, ["analyze-repo", "--no-ci"])

        assert result.exit_code == 0
        mock_run_analysis.assert_called_once()
        call_kwargs = mock_run_analysis.call_args[1]
        assert call_kwargs.get("include_ci") is False

    def test_repo_option_is_passed_to_run_analysis(self):
        """--repo option sets the repo path."""
        mock_result = MagicMock()
        mock_result.files = []

        with patch("black_box_unlock.cli.run_analysis") as mock_analysis:
            mock_analysis.return_value = mock_result
            with patch("black_box_unlock.cli.export_to_json") as mock_export:
                mock_export.return_value = "{}"
                runner.invoke(app, ["analyze-repo", "--repo", "/some/repo", "--output", "json"])

        assert mock_analysis.call_args[0][0] == Path("/some/repo")

    def test_ci_included_by_default(self):
        """Without --no-ci, include_ci defaults to True."""
        mock_result = MagicMock()
        mock_result.files = []

        with patch("black_box_unlock.cli.run_analysis") as mock_run_analysis:
            mock_run_analysis.return_value = mock_result
            with patch("black_box_unlock.cli.export_to_json") as mock_export:
                mock_export.return_value = "{}"
                result = runner.invoke(app, ["analyze-repo"])

        assert result.exit_code == 0
        mock_run_analysis.assert_called_once()
        call_kwargs = mock_run_analysis.call_args[1]
        assert call_kwargs.get("include_ci") is True


class TestAnalyzeRepoErrorHandling:
    """Tests for clean error reporting from analyze-repo."""

    def test_missing_git_prints_clean_error_not_traceback(self):
        """GitToolNotFoundError surfaces as an error message with exit code 1."""
        from black_box_unlock.core.exceptions import GitToolNotFoundError

        with patch("black_box_unlock.cli.run_analysis") as mock_analysis:
            mock_analysis.side_effect = GitToolNotFoundError("git not found on PATH")
            result = runner.invoke(app, ["analyze-repo"])

        assert result.exit_code == 1
        assert "git not found on PATH" in result.output
        assert "Traceback" not in result.output


class TestValidateCommand:
    """Tests for the validate command."""

    def test_prints_rho_per_repo(self):
        with patch("black_box_unlock.validation.validate_repo") as mock_validate:
            mock_validate.return_value = _validation_result()
            result = runner.invoke(app, ["validate", "--repo", "."])
        assert result.exit_code == 0
        assert "0.62" in result.stdout

    def test_json_output(self):
        with patch("black_box_unlock.validation.validate_repo") as mock_validate:
            mock_validate.return_value = _validation_result()
            result = runner.invoke(app, ["validate", "--repo", ".", "--json"])
        assert result.exit_code == 0
        parsed = json.loads(result.stdout)
        assert parsed[0]["spearman"] == 0.62

    def test_median_rho_for_multiple_repos(self):
        results = [
            _validation_result("a", 0.4),
            _validation_result("b", 0.6),
            _validation_result("c", 0.8),
        ]
        with patch("black_box_unlock.validation.validate_repo") as mock_validate:
            mock_validate.side_effect = results
            result = runner.invoke(app, ["validate", "--repo", "a", "--repo", "b", "--repo", "c"])
        assert result.exit_code == 0
        assert "median" in result.stdout.lower()
        assert "0.60" in result.stdout

    def test_failing_repo_reports_error_but_others_continue(self):
        with patch("black_box_unlock.validation.validate_repo") as mock_validate:
            mock_validate.side_effect = [
                InsufficientHistoryError("too little history"),
                _validation_result(),
            ]
            result = runner.invoke(app, ["validate", "--repo", "bad", "--repo", "good"])
        assert result.exit_code == 0
        assert "too little history" in result.stdout

    def test_all_repos_failing_exits_nonzero(self):
        with patch("black_box_unlock.validation.validate_repo") as mock_validate:
            mock_validate.side_effect = InsufficientHistoryError("too little history")
            result = runner.invoke(app, ["validate", "--repo", "bad"])
        assert result.exit_code == 1


def _xray_result():
    from black_box_unlock.core.models import FileXRay, FunctionChurn

    return FileXRay(
        path="mod.py",
        days=365,
        revisions_analyzed=4,
        revision_cap_hit=False,
        functions=[
            FunctionChurn(
                name="alpha",
                start_line=1,
                end_line=3,
                revisions=3,
                lines_added=6,
                lines_deleted=2,
                complexity=2.0,
            )
        ],
    )


class TestXrayCommand:
    def test_outputs_json(self):
        with patch("black_box_unlock.git.xray.xray_file") as mock_xray:
            mock_xray.return_value = _xray_result()
            result = runner.invoke(app, ["xray", "mod.py"])
        assert result.exit_code == 0
        parsed = json.loads(result.stdout)
        assert parsed["functions"][0]["name"] == "alpha"
        assert parsed["functions"][0]["hotspot_score"] == 6.0

    def test_error_exits_nonzero(self):
        from black_box_unlock.core.exceptions import NotAGitRepoError

        with patch("black_box_unlock.git.xray.xray_file") as mock_xray:
            mock_xray.side_effect = NotAGitRepoError("not a repo")
            result = runner.invoke(app, ["xray", "mod.py"])
        assert result.exit_code == 1
        assert "not a repo" in result.output

    def test_passes_options(self):
        with patch("black_box_unlock.git.xray.xray_file") as mock_xray:
            mock_xray.return_value = _xray_result()
            result = runner.invoke(
                app, ["xray", "mod.py", "--days", "90", "--cap", "50", "--repo", "."]
            )
        assert result.exit_code == 0
        kwargs = mock_xray.call_args[1]
        assert kwargs["days"] == 90 and kwargs["rev_cap"] == 50


class TestAnalyzeRepoXrayTop:
    def test_xray_top_forwarded(self):
        mock_result = MagicMock()
        mock_result.files = []
        with patch("black_box_unlock.cli.run_analysis") as mock_run:
            mock_run.return_value = mock_result
            with patch("black_box_unlock.cli.export_to_json") as mock_export:
                mock_export.return_value = "{}"
                result = runner.invoke(app, ["analyze-repo", "--xray-top", "3"])
        assert result.exit_code == 0
        assert mock_run.call_args[1]["xray_top"] == 3


class TestAnalyzeRepoJsonIntegrity:
    def test_long_json_lines_not_wrapped(self):
        # Rich console.print wraps at terminal width, corrupting JSON strings
        # longer than 80 chars (e.g. qualified function names from X-Ray)
        long_line = '{"name": "' + "x" * 200 + '"}'
        mock_result = MagicMock()
        mock_result.files = []
        with patch("black_box_unlock.cli.run_analysis") as mock_run:
            mock_run.return_value = mock_result
            with patch("black_box_unlock.cli.export_to_json") as mock_export:
                mock_export.return_value = long_line
                result = runner.invoke(app, ["analyze-repo", "--output", "json"])
        assert result.exit_code == 0
        assert long_line in result.stdout


class TestCouplingGuardCommand:
    def test_unexpected_error_is_logged_and_exits_zero(self):
        """A failure in the guard degrades to silence but leaves a diagnosable log line."""
        from loguru import logger

        messages: list[str] = []
        sink = logger.add(messages.append, level="WARNING")
        try:
            # no-op configure_logging so the CLI callback doesn't drop the test sink
            with (
                patch("black_box_unlock.cli.configure_logging"),
                patch(
                    "black_box_unlock.guard.coupling_warnings",
                    side_effect=RuntimeError("boom"),
                ),
            ):
                result = runner.invoke(app, ["coupling-guard", "src/a.py"])
        finally:
            logger.remove(sink)

        assert result.exit_code == 0
        assert any("src/a.py" in m for m in messages)


class TestXrayMinCoupling:
    def test_min_coupling_forwarded(self):
        with patch("black_box_unlock.git.xray.xray_file") as mock_xray:
            mock_xray.return_value = _xray_result()
            result = runner.invoke(app, ["xray", "mod.py", "--min-coupling", "0.5"])
        assert result.exit_code == 0
        assert mock_xray.call_args[1]["min_coupling"] == 0.5
