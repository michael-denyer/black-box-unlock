"""Unit tests for the bbu-mcp server tools."""

from datetime import datetime
from unittest.mock import patch

from black_box_unlock import mcp_server
from black_box_unlock.core.models import (
    AnalysisResult,
    AnalysisSummary,
    CouplingInfo,
    FileForensics,
)


def _result() -> AnalysisResult:
    return AnalysisResult(
        repo="demo",
        analyzed_days=30,
        generated_at=datetime(2026, 6, 12),
        files=[
            FileForensics(
                path="src/auth.py",
                commits=10,
                lines_changed=500,
                complexity=40.0,
                authors=["a@x.com"],
                coupled_with=[CouplingInfo(file="src/token.py", ratio=0.8)],
                build_failures=2,
                bugfix_commits=3,
            ),
            FileForensics(
                path="src/util.py",
                commits=2,
                lines_changed=20,
                complexity=5.0,
                authors=["a@x.com"],
                coupled_with=[],
            ),
        ],
        summary=AnalysisSummary(total_files=2, high_risk_ownership=0, coupled_pairs=1),
    )


@patch("black_box_unlock.mcp_server._analysis")
class TestMcpTools:
    def test_get_hotspots_returns_top_n_sorted(self, mock_analysis):
        mock_analysis.return_value = _result()

        hotspots = mcp_server.get_hotspots(repo_path=".", days=30, top_n=1)

        assert len(hotspots) == 1
        assert hotspots[0]["path"] == "src/auth.py"
        assert hotspots[0]["hotspot_score"] == 400.0
        assert hotspots[0]["bugfix_commits"] == 3

    def test_get_file_forensics_finds_file(self, mock_analysis):
        mock_analysis.return_value = _result()

        info = mcp_server.get_file_forensics("src/auth.py", repo_path=".", days=30)

        assert info["commits"] == 10
        assert info["build_failures"] == 2

    def test_get_file_forensics_unknown_file(self, mock_analysis):
        mock_analysis.return_value = _result()

        info = mcp_server.get_file_forensics("nope.py", repo_path=".", days=30)

        assert "error" in info

    def test_get_coupled_files(self, mock_analysis):
        mock_analysis.return_value = _result()

        coupled = mcp_server.get_coupled_files("src/auth.py", repo_path=".", days=30)

        assert coupled == [{"file": "src/token.py", "ratio": 0.8}]

    def test_get_ci_failures_only_nonzero(self, mock_analysis):
        mock_analysis.return_value = _result()

        failures = mcp_server.get_ci_failures(repo_path=".", days=30)

        assert failures == [{"path": "src/auth.py", "build_failures": 2}]


class TestAnalysisCache:
    @patch("black_box_unlock.mcp_server.run_analysis")
    def test_same_args_hit_cache(self, mock_run):
        mock_run.return_value = _result()
        mcp_server._cache.clear()

        mcp_server._analysis(".", 30)
        mcp_server._analysis(".", 30)

        assert mock_run.call_count == 1
