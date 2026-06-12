"""Unit tests for the bbu-mcp server tools."""

import asyncio
from datetime import datetime
from unittest.mock import patch

import pytest

from black_box_unlock import mcp_server
from black_box_unlock.core.exceptions import NotAGitRepoError
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

    def test_get_file_forensics_unknown_file_raises(self, mock_analysis):
        mock_analysis.return_value = _result()

        with pytest.raises(ValueError, match="No history for nope.py"):
            mcp_server.get_file_forensics("nope.py", repo_path=".", days=30)

    def test_get_coupled_files(self, mock_analysis):
        mock_analysis.return_value = _result()

        coupled = mcp_server.get_coupled_files("src/auth.py", repo_path=".", days=30)

        assert coupled == [{"file": "src/token.py", "ratio": 0.8}]

    def test_get_ci_failures_only_nonzero(self, mock_analysis):
        mock_analysis.return_value = _result()

        failures = mcp_server.get_ci_failures(repo_path=".")

        assert failures == [{"path": "src/auth.py", "build_failures": 2}]

    def test_get_ownership_unknown_file_raises(self, mock_analysis):
        mock_analysis.return_value = _result()

        with pytest.raises(ValueError, match="No history for nope.py"):
            mcp_server.get_ownership("nope.py", repo_path=".", days=30)

    def test_bad_repo_raises_value_error(self, mock_analysis):
        mock_analysis.side_effect = NotAGitRepoError("Not a git repository: /tmp")

        with pytest.raises(ValueError, match="Not a git repository: /tmp"):
            mcp_server.get_hotspots(repo_path="/tmp", days=1)


class TestAnalysisCache:
    @patch("black_box_unlock.mcp_server.run_analysis")
    def test_same_args_hit_cache(self, mock_run):
        mock_run.return_value = _result()
        mcp_server._cache.clear()

        mcp_server._analysis(".", 30, False)
        mcp_server._analysis(".", 30, False)

        assert mock_run.call_count == 1

    @patch("black_box_unlock.mcp_server.run_analysis")
    def test_different_include_ci_are_separate_cache_entries(self, mock_run):
        mock_run.return_value = _result()
        mcp_server._cache.clear()

        mcp_server._analysis(".", 30, False)
        mcp_server._analysis(".", 30, True)

        assert mock_run.call_count == 2


class TestToolRegistration:
    def test_all_six_tools_registered(self):
        names = {t.name for t in asyncio.run(mcp_server.mcp.list_tools())}
        assert names == {
            "get_hotspots",
            "get_file_forensics",
            "get_coupled_files",
            "get_ownership",
            "get_ci_failures",
            "get_flaky_steps",
        }
