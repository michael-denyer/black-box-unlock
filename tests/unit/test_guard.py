"""Unit tests for the coupling guard."""

import json
from unittest.mock import patch

from black_box_unlock.guard import coupling_warnings


def _cache_payload() -> dict:
    return {
        "files": [
            {
                "path": "src/auth.py",
                "coupled_with": [
                    {"file": "src/token.py", "ratio": 0.8},
                    {"file": "src/util.py", "ratio": 0.3},
                ],
            },
        ]
    }


class TestCouplingWarnings:
    def test_warns_above_threshold_only(self, tmp_path):
        cache = tmp_path / ".bbu" / "cache.json"
        cache.parent.mkdir()
        cache.write_text(json.dumps(_cache_payload()))

        warnings = coupling_warnings("src/auth.py", tmp_path, threshold=0.5)

        assert len(warnings) == 1
        assert "src/token.py" in warnings[0]
        assert "80%" in warnings[0]

    def test_unknown_file_no_warnings(self, tmp_path):
        cache = tmp_path / ".bbu" / "cache.json"
        cache.parent.mkdir()
        cache.write_text(json.dumps(_cache_payload()))

        assert coupling_warnings("src/new.py", tmp_path) == []

    @patch("black_box_unlock.guard.run_analysis")
    def test_builds_cache_when_missing(self, mock_run, tmp_path):
        from datetime import datetime

        from black_box_unlock.core.models import AnalysisResult, AnalysisSummary

        (tmp_path / ".git").mkdir()
        mock_run.return_value = AnalysisResult(
            repo="t",
            analyzed_days=90,
            generated_at=datetime(2026, 6, 12),
            files=[],
            summary=AnalysisSummary(total_files=0, high_risk_ownership=0, coupled_pairs=0),
        )

        coupling_warnings("src/auth.py", tmp_path)

        mock_run.assert_called_once()
        assert (tmp_path / ".bbu" / "cache.json").exists()
