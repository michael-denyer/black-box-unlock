"""Tests for the stable browser-data boundary."""

from datetime import datetime, timezone

from black_box_unlock.core.models import (
    AnalysisResult,
    AnalysisSummary,
    FileForensics,
    TemporalCoupling,
)
from black_box_unlock.visualization.report_data import build_report_payload


def _result(*, couplings: list[TemporalCoupling] | None = None) -> AnalysisResult:
    return AnalysisResult(
        repo="forensics",
        analyzed_days=30,
        generated_at=datetime(2026, 1, 25, 15, 30, tzinfo=timezone.utc),
        files=[
            FileForensics(
                path="src/strong.py",
                commits=10,
                lines_changed=200,
                complexity=8,
                authors=["Ada", "Grace"],
                coupled_with=[],
                bugfix_commits=3,
                build_failures=2,
            ),
            FileForensics(
                path="src/tiny.py",
                commits=1,
                lines_changed=10,
                complexity=2,
                authors=["Ada"],
                coupled_with=[],
            ),
            FileForensics(
                path="src/partner.py",
                commits=12,
                lines_changed=100,
                complexity=4,
                authors=["Grace"],
                coupled_with=[],
            ),
        ],
        couplings=couplings or [],
        summary=AnalysisSummary(
            total_files=3,
            high_risk_ownership=0,
            coupled_pairs=len(couplings or []),
        ),
    )


def test_couplings_are_ordered_by_supported_confidence_before_raw_ratio() -> None:
    payload = build_report_payload(
        _result(
            couplings=[
                TemporalCoupling(
                    file_a="src/tiny.py",
                    file_b="src/partner.py",
                    co_change_count=1,
                    commits_a=1,
                    commits_b=12,
                ),
                TemporalCoupling(
                    file_a="src/strong.py",
                    file_b="src/partner.py",
                    co_change_count=8,
                    commits_a=10,
                    commits_b=12,
                ),
            ]
        )
    )

    assert payload["couplings"][0]["file_a"] == "src/strong.py"
    assert (
        payload["couplings"][0]["confidence_lower_bound"]
        > payload["couplings"][1]["confidence_lower_bound"]
    )
    assert payload["couplings"][1]["raw_ratio"] == 1.0


def test_coupling_projection_keeps_support_and_both_revision_counts() -> None:
    payload = build_report_payload(
        _result(
            couplings=[
                TemporalCoupling(
                    file_a="src/strong.py",
                    file_b="src/partner.py",
                    co_change_count=8,
                    commits_a=10,
                    commits_b=12,
                )
            ]
        )
    )

    row = payload["couplings"][0]
    assert row == {
        "key": "src/strong.py\0src/partner.py",
        "file_a": "src/strong.py",
        "file_b": "src/partner.py",
        "role_a": "source",
        "role_b": "source",
        "shared_revisions": 8,
        "revisions_a": 10,
        "revisions_b": 12,
        "denominator": 10,
        "raw_ratio": 0.8,
        "confidence_lower_bound": row["confidence_lower_bound"],
    }


def test_complete_analysis_shape_is_retained_and_files_are_stable() -> None:
    payload = build_report_payload(_result())

    assert payload["schema_version"] == 2
    assert payload["analysis"]["parameters"]["max_coupled_files_per_commit"] == 50
    assert payload["analysis"]["ci_status"]["state"] == "disabled"
    assert payload["analysis"]["files"][0]["path"] == "src/strong.py"
    assert payload["analysis"]["files"][0]["bugfix_commits"] == 3
    assert payload["analysis"]["files"][0]["build_failures"] == 2
    assert payload["analysis"]["files"][0]["path_role"] == "source"
    assert payload["analysis"]["files"][0]["path_role_rule"] == "source-extension"


def test_report_roles_separate_code_from_repository_support_files() -> None:
    result = _result()

    def support_file(
        path: str, *, commits: int, lines_changed: int, complexity: int
    ) -> FileForensics:
        return FileForensics(
            path=path,
            commits=commits,
            lines_changed=lines_changed,
            complexity=complexity,
            authors=[],
            coupled_with=[],
        )

    result.files.extend(
        [
            support_file("README.md", commits=5, lines_changed=20, complexity=12),
            support_file("uv.lock", commits=4, lines_changed=100, complexity=0),
            support_file(".claude-plugin/plugin.json", commits=2, lines_changed=8, complexity=0),
            support_file(".gitignore", commits=2, lines_changed=4, complexity=0),
            support_file("migrations/001_create.py", commits=3, lines_changed=30, complexity=3),
        ]
    )

    payload = build_report_payload(result)
    roles = {file["path"]: file["path_role"] for file in payload["analysis"]["files"]}

    assert roles == {
        ".claude-plugin/plugin.json": "config",
        ".gitignore": "other",
        "README.md": "docs",
        "migrations/001_create.py": "migration",
        "src/partner.py": "source",
        "src/strong.py": "source",
        "src/tiny.py": "source",
        "uv.lock": "generated",
    }
