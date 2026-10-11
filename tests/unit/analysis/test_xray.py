"""Unit tests for the automatic X-Ray of the top hotspots."""

from unittest.mock import patch

from black_box_unlock.analysis import run_analysis
from tests.factories import make_commit


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
        with patch("black_box_unlock.git.history.fetch_git_history") as mock_hist:
            mock_hist.return_value = self._history()
            with patch("black_box_unlock.analysis.xray_file") as mock_xray:
                mock_xray.return_value = fake
                result = run_analysis(tmp_path, days=30, include_ci=False, xray_top=1)
        assert result.files[0].functions[0].name == "f"
        assert result.summary.xrayed_files == 1
        assert result.files[0].xray_failed is False  # a clean X-Ray is not flagged failed

    def test_xray_top_zero_disables(self, tmp_path):
        (tmp_path / "mod.py").write_text("def f():\n    return 1\n")
        with patch("black_box_unlock.git.history.fetch_git_history") as mock_hist:
            mock_hist.return_value = self._history()
            with patch("black_box_unlock.analysis.xray_file") as mock_xray:
                result = run_analysis(tmp_path, days=30, include_ci=False, xray_top=0)
        mock_xray.assert_not_called()
        assert result.summary.xrayed_files == 0

    def test_xray_failure_degrades_gracefully(self, tmp_path):
        (tmp_path / "mod.py").write_text("def f():\n    return 1\n")
        with patch("black_box_unlock.git.history.fetch_git_history") as mock_hist:
            mock_hist.return_value = self._history()
            with patch("black_box_unlock.analysis.xray_file") as mock_xray:
                mock_xray.side_effect = RuntimeError("boom")
                result = run_analysis(tmp_path, days=30, include_ci=False, xray_top=1)
        assert result.files[0].functions == []
        assert result.summary.xrayed_files == 0
        # functions == [] alone can't distinguish a crash from "no functions";
        # xray_failed makes the degraded result observable to JSON/MCP consumers.
        assert result.files[0].xray_failed is True
