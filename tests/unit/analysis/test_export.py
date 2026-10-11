"""Unit tests for export_to_json."""

import json
from datetime import datetime

from black_box_unlock.analysis import export_to_json
from black_box_unlock.core.models import (
    AnalysisResult,
    AnalysisSummary,
    CouplingInfo,
    FileForensics,
)
from black_box_unlock.path_roles import PathRole
from tests.factories import make_provenance


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
                    path_role=PathRole.source,
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
            provenance=make_provenance(),
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
                    path_role=PathRole.source,
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
            provenance=make_provenance(),
        )

        json_str = export_to_json(result)
        parsed = json.loads(json_str)

        # Computed properties should be in output
        assert parsed["files"][0]["hotspot_score"] == 2000  # 10 commits * 200.0 complexity
        assert parsed["files"][0]["author_count"] == 4
        assert parsed["files"][0]["is_high_risk"] is True
