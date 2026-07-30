"""Tests for the standalone HTML investigation report."""

import re
from datetime import datetime, timezone

from black_box_unlock.core.models import (
    AnalysisResult,
    AnalysisSummary,
    FileForensics,
    TemporalCoupling,
)
from black_box_unlock.visualization.html import generate_html_report


def _result(*, repo: str = "test-repo", path: str = "src/auth.py") -> AnalysisResult:
    return AnalysisResult(
        repo=repo,
        analyzed_days=30,
        generated_at=datetime(2026, 1, 25, 15, 30, tzinfo=timezone.utc),
        files=[
            FileForensics(
                path=path,
                commits=10,
                lines_changed=200,
                complexity=20,
                authors=["alice@example.com", "bob@example.com"],
                coupled_with=[],
                bugfix_commits=2,
                build_failures=1,
            ),
            FileForensics(
                path="src/user.py",
                commits=12,
                lines_changed=150,
                complexity=8,
                authors=["alice@example.com"],
                coupled_with=[],
            ),
        ],
        couplings=[
            TemporalCoupling(
                file_a=path,
                file_b="src/user.py",
                co_change_count=8,
                commits_a=10,
                commits_b=12,
            )
        ],
        summary=AnalysisSummary(
            total_files=2,
            high_risk_ownership=0,
            coupled_pairs=1,
            xrayed_files=0,
        ),
    )


def test_generates_one_complete_investigation_workspace() -> None:
    document = generate_html_report(_result())

    assert document.startswith("<!doctype html>")
    assert document.endswith("</html>\n")
    assert 'data-testid="file-grid"' in document
    assert 'data-testid="coupling-grid"' in document
    assert 'id="selected-file-heading"' in document
    assert 'id="risk-matrix"' in document
    assert 'id="repository-map"' in document
    assert "Confidence-first temporal coupling" in document


def test_report_is_self_contained_and_denies_connections() -> None:
    document = generate_html_report(_result())

    external_resources = re.findall(
        r"""(?:src|href)\s*=\s*["'](?:https?:)?//""",
        document,
        flags=re.IGNORECASE,
    )
    assert external_resources == []
    assert "connect-src 'none'" in document
    assert '<script src="' not in document
    assert '<link rel="stylesheet"' not in document
    assert "echarts.init" in document
    assert "new Tabulator" in document


def test_embeds_complete_confidence_evidence() -> None:
    document = generate_html_report(_result())

    assert '"shared_revisions":8' in document
    assert '"revisions_a":10' in document
    assert '"revisions_b":12' in document
    assert '"denominator":10' in document
    assert '"raw_ratio":0.8' in document
    assert '"confidence_lower_bound":' in document


def test_repository_strings_cannot_create_markup_or_end_data_script() -> None:
    marker = '</script><img src=x onerror="globalThis.BBU_INJECTED=1">'
    document = generate_html_report(_result(repo=marker, path=marker))

    assert marker not in document
    assert "\\u003c/script\\u003e" in document
    assert "\\u003cimg src=x onerror=" in document


def test_same_result_generates_identical_document() -> None:
    result = _result()

    assert generate_html_report(result) == generate_html_report(result)


def test_report_has_keyboard_and_non_canvas_evidence_paths() -> None:
    document = generate_html_report(_result())

    assert 'role="tablist"' in document
    assert 'aria-controls="panel-coupling"' in document
    assert "Use Tab then Enter on Inspect." in document
    assert "Sort with column headers." in document
    assert "Both revision counts remain visible." in document
