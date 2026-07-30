"""Tests for the pure change-review decision."""

from datetime import datetime, timezone

from black_box_unlock.core.models import (
    AnalysisResult,
    AnalysisSummary,
    FileForensics,
    SignalStatus,
    TemporalCoupling,
)
from black_box_unlock.git.changes import (
    ChangedPath,
    ChangeKind,
    ChangeSet,
    WorkingTreeChange,
    WorkingTreeProvenance,
)
from black_box_unlock.review import ChangeReview, NoChanges, ReviewParameters, project_change_review


def _change_set(*paths: str) -> ChangeSet:
    return ChangeSet(
        selector=WorkingTreeChange(),
        provenance=WorkingTreeProvenance(
            head_oid="abc123",
            observed_at=datetime(2026, 7, 30, tzinfo=timezone.utc),
        ),
        paths=[ChangedPath(path=path, kind=ChangeKind.modified) for path in paths],
    )


def _analysis() -> AnalysisResult:
    return AnalysisResult(
        repo="demo",
        analyzed_days=90,
        generated_at=datetime(2026, 7, 30, tzinfo=timezone.utc),
        files=[
            FileForensics(
                path="src/a.py",
                commits=13,
                lines_changed=100,
                complexity=10,
                authors=["a@example.com"],
                coupled_with=[],
                bugfix_commits=2,
            ),
            FileForensics(
                path="tests/test_a.py",
                commits=13,
                lines_changed=80,
                complexity=5,
                authors=["a@example.com"],
                coupled_with=[],
            ),
        ],
        couplings=[
            TemporalCoupling(
                file_a="src/a.py",
                file_b="tests/test_a.py",
                co_change_count=11,
                commits_a=13,
                commits_b=13,
            )
        ],
        summary=AnalysisSummary(total_files=2, high_risk_ownership=0, coupled_pairs=1),
        ci_status=SignalStatus(),
    )


def test_no_selected_paths_has_an_explicit_result():
    result = project_change_review(_change_set(), _analysis(), ReviewParameters())

    assert isinstance(result, NoChanges)
    assert result.kind == "no_changes"
    assert result.ci_status.state.value == "disabled"


def test_missing_repeated_companion_is_the_first_action():
    result = project_change_review(_change_set("src/a.py"), _analysis(), ReviewParameters())

    assert isinstance(result, ChangeReview)
    assert result.actions[0].kind == "check_coupled_paths"
    evidence = result.actions[0].evidence[0]
    assert evidence.coupled_path == "tests/test_a.py"
    assert evidence.shared_revisions == 11
    assert evidence.changed_path_revisions == 13


def test_changed_companion_is_covered_not_recommended():
    result = project_change_review(
        _change_set("src/a.py", "tests/test_a.py"),
        _analysis(),
        ReviewParameters(),
    )

    assert isinstance(result, ChangeReview)
    assert all(action.kind != "check_coupled_paths" for action in result.actions)
    assert result.couplings[0].coupled_path_is_changed is True


def test_action_list_is_bounded_to_three():
    analysis = _analysis()
    analysis.couplings.extend(
        TemporalCoupling(
            file_a="src/a.py",
            file_b=f"src/partner_{index}.py",
            co_change_count=5,
            commits_a=13,
            commits_b=6,
        )
        for index in range(6)
    )

    result = project_change_review(_change_set("src/a.py"), analysis, ReviewParameters())

    assert isinstance(result, ChangeReview)
    assert len(result.actions) <= 3


def test_primary_evidence_list_is_bounded():
    analysis = _analysis()
    analysis.couplings.extend(
        TemporalCoupling(
            file_a="src/a.py",
            file_b=f"src/partner_{index}.py",
            co_change_count=5,
            commits_a=13,
            commits_b=6,
        )
        for index in range(25)
    )

    result = project_change_review(_change_set("src/a.py"), analysis, ReviewParameters())

    assert isinstance(result, ChangeReview)
    assert len(result.couplings) == 20


def test_documentation_change_does_not_create_production_actions():
    analysis = _analysis()
    analysis.files.append(
        FileForensics(
            path="docs/guide.md",
            commits=9,
            lines_changed=100,
            complexity=4,
            authors=["a@example.com"],
            coupled_with=[],
            bugfix_commits=3,
        )
    )
    analysis.couplings.append(
        TemporalCoupling(
            file_a="docs/guide.md",
            file_b="docs/other.md",
            co_change_count=5,
            commits_a=9,
            commits_b=5,
        )
    )

    result = project_change_review(_change_set("docs/guide.md"), analysis, ReviewParameters())

    assert isinstance(result, ChangeReview)
    assert result.actions == []
