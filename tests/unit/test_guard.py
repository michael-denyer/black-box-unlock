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

    def test_tied_ratios_break_by_path_ascending(self, tmp_path):
        """Equal ratios must name files deterministically, not in cache order."""
        payload = {
            "files": [
                {
                    "path": "src/hub.py",
                    "coupled_with": [
                        {"file": "zeta.py", "ratio": 1.0},
                        {"file": "alpha.py", "ratio": 1.0},
                        {"file": "mid.py", "ratio": 1.0},
                        {"file": "beta.py", "ratio": 1.0},
                    ],
                },
            ]
        }
        cache = tmp_path / ".bbu" / "cache.json"
        cache.parent.mkdir()
        cache.write_text(json.dumps(payload))

        warnings = coupling_warnings("src/hub.py", tmp_path)

        assert "alpha.py" in warnings[0]
        assert "beta.py" in warnings[1]
        assert "mid.py" in warnings[2]
        assert "+1 more" in warnings[3]

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
        assert (tmp_path / ".bbu" / ".gitignore").read_text() == "*\n"

    def test_warnings_sorted_and_capped_at_top_3(self, tmp_path):
        payload = {
            "files": [
                {
                    "path": "src/hub.py",
                    "coupled_with": [
                        {"file": "a.py", "ratio": 0.55},
                        {"file": "b.py", "ratio": 1.0},
                        {"file": "c.py", "ratio": 0.7},
                        {"file": "d.py", "ratio": 0.9},
                        {"file": "e.py", "ratio": 0.6},
                    ],
                },
            ]
        }
        cache = tmp_path / ".bbu" / "cache.json"
        cache.parent.mkdir()
        cache.write_text(json.dumps(payload))

        warnings = coupling_warnings("src/hub.py", tmp_path, threshold=0.5)

        assert len(warnings) == 4  # top 3 + the "+2 more" line
        assert "b.py" in warnings[0] and "100%" in warnings[0]
        assert "d.py" in warnings[1]
        assert "c.py" in warnings[2]
        assert "+2 more" in warnings[3]

    def test_stale_cache_is_rebuilt_fresh_cache_served(self, tmp_path):
        import os
        import time as time_mod

        cache = tmp_path / ".bbu" / "cache.json"
        cache.parent.mkdir()
        cache.write_text(json.dumps({"files": []}))
        # fresh cache: no rebuild
        with patch("black_box_unlock.guard.run_analysis") as mock_run:
            coupling_warnings("x.py", tmp_path)
            mock_run.assert_not_called()
        # stale cache (25h old): rebuild
        old = time_mod.time() - 25 * 3600
        os.utime(cache, (old, old))
        (tmp_path / ".git").mkdir()
        from datetime import datetime

        from black_box_unlock.core.models import AnalysisResult, AnalysisSummary

        with patch("black_box_unlock.guard.run_analysis") as mock_run:
            mock_run.return_value = AnalysisResult(
                repo="t",
                analyzed_days=90,
                generated_at=datetime(2026, 6, 12),
                files=[],
                summary=AnalysisSummary(total_files=0, high_risk_ownership=0, coupled_pairs=0),
            )
            coupling_warnings("x.py", tmp_path)
            mock_run.assert_called_once()
