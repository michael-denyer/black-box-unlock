"""Unit tests for CLI commands."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from black_box_unlock.cli import app

runner = CliRunner()


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

    def test_missing_gmap_prints_clean_error_not_traceback(self):
        """GitToolNotFoundError surfaces as an error message with exit code 1."""
        from black_box_unlock.core.exceptions import GitToolNotFoundError

        with patch("black_box_unlock.cli.run_analysis") as mock_analysis:
            mock_analysis.side_effect = GitToolNotFoundError(
                "gmap CLI not found. Install it with: cargo install gmap"
            )
            result = runner.invoke(app, ["analyze-repo"])

        assert result.exit_code == 1
        assert "gmap CLI not found" in result.output
        assert "Traceback" not in result.output
