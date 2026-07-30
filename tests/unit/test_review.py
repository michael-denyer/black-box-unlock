"""Tests for the pure change-review decision."""

from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from black_box_unlock.core.exceptions import ConfigurationError
from black_box_unlock.core.models import (
    AnalysisResult,
    AnalysisSummary,
    FailedWorkflowRun,
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
from black_box_unlock.path_roles import PathRole, PathRoleRule
from black_box_unlock.review import (
    ChangeReview,
    ChangeReviewRequest,
    NoChanges,
    ReviewParameters,
    project_change_review,
    run_change_review,
)


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


@patch("black_box_unlock.review.collect_change_set")
def test_change_review_request_resolves_public_defaults(mock_collect, tmp_path):
    mock_collect.return_value = _change_set()

    result = run_change_review(
        tmp_path,
        ChangeReviewRequest(selector=WorkingTreeChange()),
    )

    assert isinstance(result, NoChanges)
    assert result.parameters.model_dump() == {
        "days": 90,
        "min_coupling": 0.3,
        "min_shared_revisions": 2,
        "include_ci": False,
        "max_actions": 3,
        "profile": "default",
        "config_path": None,
    }


@patch("black_box_unlock.review.collect_change_set")
def test_request_overrides_win_over_the_named_profile(mock_collect, tmp_path):
    (tmp_path / ".bbu.toml").write_text(
        """
[profiles.release]
days = 180
include_ci = true
""".strip()
        + "\n"
    )
    mock_collect.return_value = _change_set()

    result = run_change_review(
        tmp_path,
        ChangeReviewRequest(
            selector=WorkingTreeChange(),
            profile="release",
            days=30,
            include_ci=False,
        ),
    )

    assert isinstance(result, NoChanges)
    assert result.parameters.days == 30
    assert result.parameters.include_ci is False
    assert result.parameters.profile == "release"
    assert result.parameters.config_path == ".bbu.toml"


def test_unknown_request_profile_lists_available_names(tmp_path):
    (tmp_path / ".bbu.toml").write_text("[profiles.release]\ndays = 180\n")

    with pytest.raises(ConfigurationError, match="available profiles: release"):
        run_change_review(
            tmp_path,
            ChangeReviewRequest(
                selector=WorkingTreeChange(),
                profile="missing",
            ),
        )


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


def test_copy_starts_a_new_identity_without_source_coupling():
    change_set = ChangeSet(
        selector=WorkingTreeChange(),
        provenance=WorkingTreeProvenance(
            head_oid="abc123",
            observed_at=datetime(2026, 7, 30, tzinfo=timezone.utc),
        ),
        paths=[
            ChangedPath(
                path="src/copied.py",
                previous_path="src/a.py",
                kind=ChangeKind.copied,
            )
        ],
    )
    analysis = _analysis()
    analysis.failed_ci_runs = [
        FailedWorkflowRun(
            run_id=42,
            workflow_name="CI",
            run_url="https://github.com/example/demo/actions/runs/42",
            commit_sha="deadbeef",
            conclusion="failure",
            created_at=datetime(2026, 7, 29, tzinfo=timezone.utc),
            implicated_paths=["src/a.py"],
        )
    ]

    result = project_change_review(
        change_set,
        analysis,
        ReviewParameters(include_ci=True),
    )

    assert isinstance(result, ChangeReview)
    assert result.files[0].evidence.commits == 0
    assert result.files[0].evidence.bugfix_commits == 0
    assert result.files[0].evidence.author_count == 0
    assert result.couplings == []
    assert all(action.kind != "inspect_ci_failures" for action in result.actions)


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


def test_project_path_role_overrides_the_builtin_classifier():
    result = project_change_review(
        _change_set("templates/account.tmpl"),
        _analysis(),
        ReviewParameters(),
        path_role_rules=(PathRoleRule(pattern="templates/**", role=PathRole.source),),
    )

    assert isinstance(result, ChangeReview)
    assert result.files[0].evidence.role.model_dump() == {
        "role": PathRole.source,
        "rule": "project:templates/**",
    }
    test_action = next(action for action in result.actions if action.kind == "add_or_update_tests")
    assert test_action.evidence.role_classifier_version == 2


def test_ci_action_keeps_run_details_and_states_attribution_limit():
    analysis = _analysis()
    analysis.failed_ci_runs = [
        FailedWorkflowRun(
            run_id=42,
            workflow_name="CI",
            run_url="https://github.com/example/demo/actions/runs/42",
            commit_sha="deadbeef",
            conclusion="failure",
            created_at=datetime(2026, 7, 29, tzinfo=timezone.utc),
            implicated_paths=["src/a.py", "src/unrelated.py"],
        )
    ]

    result = project_change_review(
        _change_set("src/a.py"),
        analysis,
        ReviewParameters(include_ci=True),
    )

    assert isinstance(result, ChangeReview)
    action = next(action for action in result.actions if action.kind == "inspect_ci_failures")
    assert "not proven causal" in action.message
    assert action.evidence[0].model_dump(mode="json") == {
        "run_id": 42,
        "workflow_name": "CI",
        "run_url": "https://github.com/example/demo/actions/runs/42",
        "commit_sha": "deadbeef",
        "conclusion": "failure",
        "created_at": "2026-07-29T00:00:00Z",
        "implicated_changed_paths": ["src/a.py"],
        "attribution": "changed_in_failed_commit",
    }


def test_failed_run_without_a_selected_path_does_not_create_an_action():
    analysis = _analysis()
    analysis.failed_ci_runs = [
        FailedWorkflowRun(
            run_id=42,
            workflow_name="CI",
            run_url="https://github.com/example/demo/actions/runs/42",
            commit_sha="deadbeef",
            conclusion="failure",
            created_at=datetime(2026, 7, 29, tzinfo=timezone.utc),
            implicated_paths=["src/unrelated.py"],
        )
    ]

    result = project_change_review(
        _change_set("src/a.py"),
        analysis,
        ReviewParameters(include_ci=True),
    )

    assert isinstance(result, ChangeReview)
    assert all(action.kind != "inspect_ci_failures" for action in result.actions)


def test_ci_evidence_cannot_create_an_action_when_the_signal_is_disabled():
    analysis = _analysis()
    analysis.failed_ci_runs = [
        FailedWorkflowRun(
            run_id=42,
            workflow_name="CI",
            run_url="https://github.com/example/demo/actions/runs/42",
            commit_sha="deadbeef",
            conclusion="failure",
            created_at=datetime(2026, 7, 29, tzinfo=timezone.utc),
            implicated_paths=["src/a.py"],
        )
    ]

    result = project_change_review(
        _change_set("src/a.py"),
        analysis,
        ReviewParameters(include_ci=False),
    )

    assert isinstance(result, ChangeReview)
    assert all(action.kind != "inspect_ci_failures" for action in result.actions)
