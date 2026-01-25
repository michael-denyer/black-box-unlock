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
