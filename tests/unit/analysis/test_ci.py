"""Unit tests for CI signals inside the analysis pipeline."""

import json
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from black_box_unlock.analysis import export_to_json, run_analysis
from black_box_unlock.cicd.models import CIAnalysis
from black_box_unlock.core.models import (
    FailedWorkflowRun,
    FlakyStepStats,
    SignalState,
    SignalStatus,
)
from tests.factories import make_commit


class TestCIInPipeline:
    """CI collection crosses one typed seam into repository analysis."""

    @patch("black_box_unlock.analysis.collect_ci_signals")
    @patch("black_box_unlock.git.history.fetch_git_history")
    def test_includes_ci_data_and_status(self, mock_history, mock_ci):
        mock_history.return_value = [
            make_commit(
                author_email="test@example.com",
                files=[{"path": "src/main.py", "added_lines": 10, "deleted_lines": 5}],
            )
        ]
        mock_ci.return_value = CIAnalysis(
            status=SignalStatus(state=SignalState.available),
            file_failures={"src/main.py": 2},
            failed_runs=[
                FailedWorkflowRun(
                    run_id=42,
                    workflow_name="CI",
                    run_url="https://github.com/example/repo/actions/runs/42",
                    commit_sha="abc123",
                    conclusion="failure",
                    created_at=datetime(2026, 6, 2),
                    implicated_paths=["src/main.py"],
                )
            ],
            flaky_steps=[
                FlakyStepStats(
                    job_name="test",
                    step_name="Run tests",
                    first_seen=datetime(2026, 6, 1),
                    last_seen=datetime(2026, 6, 2),
                    runs=1,
                    flaky_runs=1,
                    total_attempts=2,
                    failures=1,
                    flaky_count=1,
                )
            ],
        )

        result = run_analysis(Path("/fake/repo"), days=30, include_ci=True)

        assert mock_ci.call_args.kwargs["days"] == 30
        main_file = next(file for file in result.files if file.path == "src/main.py")
        assert main_file.build_failures == 2
        assert result.flaky_steps[0].step_name == "Run tests"
        assert result.failed_ci_runs[0].run_id == 42
        assert result.ci_status.state is SignalState.available

    @patch("black_box_unlock.analysis.collect_ci_signals")
    @patch("black_box_unlock.git.history.fetch_git_history")
    def test_ci_failures_under_a_former_name_count_on_the_current_path(self, mock_history, mock_ci):
        """A failed run that touched a.py before its rename implicates b.py; a reused name does not move."""
        mock_history.return_value = [
            make_commit(files=[{"path": "b.py", "former_paths": ["a.py"]}]),
            make_commit(files=[{"path": "c.py", "former_paths": ["d.py"]}, {"path": "d.py"}]),
        ]
        mock_ci.return_value = CIAnalysis(
            status=SignalStatus(state=SignalState.available),
            file_failures={"a.py": 1, "d.py": 1},
            failed_runs=[
                FailedWorkflowRun(
                    run_id=7,
                    workflow_name="CI",
                    run_url="https://github.com/example/repo/actions/runs/7",
                    commit_sha="abc123",
                    conclusion="failure",
                    created_at=datetime(2026, 6, 2),
                    implicated_paths=["a.py", "d.py"],
                )
            ],
        )

        result = run_analysis(Path("/fake/repo"), include_ci=True, xray_top=0)

        failures = {file.path: file.build_failures for file in result.files}
        assert failures == {"b.py": 1, "c.py": 0, "d.py": 1}
        assert result.failed_ci_runs[0].implicated_paths == ["b.py", "d.py"]

    @patch("black_box_unlock.analysis.collect_ci_signals")
    @patch("black_box_unlock.git.history.fetch_git_history")
    def test_ci_only_files_remain_visible(self, mock_history, mock_ci):
        mock_history.return_value = []
        mock_ci.return_value = CIAnalysis(
            status=SignalStatus(state=SignalState.available),
            file_failures={"src/old_failure.py": 3},
        )

        result = run_analysis(Path("/fake/repo"), include_ci=True, xray_top=0)

        assert [(file.path, file.build_failures) for file in result.files] == [
            ("src/old_failure.py", 3)
        ]

    @patch("black_box_unlock.analysis.collect_ci_signals")
    @patch("black_box_unlock.git.history.fetch_git_history")
    def test_no_ci_skips_collection_and_records_disabled(self, mock_history, mock_ci):
        mock_history.return_value = []

        result = run_analysis(Path("/fake/repo"), include_ci=False)

        mock_ci.assert_not_called()
        assert result.ci_status.state is SignalState.disabled
        assert result.parameters.include_ci is False

    @patch("black_box_unlock.analysis.collect_ci_signals")
    @patch("black_box_unlock.git.history.fetch_git_history")
    def test_include_ci_defaults_to_true(self, mock_history, mock_ci):
        mock_history.return_value = []
        mock_ci.return_value = CIAnalysis(
            status=SignalStatus(state=SignalState.unavailable, errors=["gh unavailable"])
        )

        result = run_analysis(Path("/fake/repo"))

        mock_ci.assert_called_once_with(repo_path=Path("/fake/repo"), limit=100, days=30)
        assert result.ci_status.state is SignalState.unavailable
        assert result.ci_status.errors == ["gh unavailable"]

    def test_includes_bugfix_commit_counts(self):
        history = [
            make_commit(
                author_email="a@x.com",
                message="fix: crash on empty input",
                files=[{"path": "src/auth.py", "added_lines": 5, "deleted_lines": 1}],
            )
        ]

        with patch("black_box_unlock.git.history.fetch_git_history", return_value=history):
            result = run_analysis(Path("/fake/repo"), days=30, include_ci=False)

        auth = next(file for file in result.files if file.path == "src/auth.py")
        assert auth.bugfix_commits == 1

    def test_path_role_uses_builtin_classifier(self):
        history = [
            make_commit(
                author_email="a@x.com",
                files=[
                    {"path": "src/hooks/useThing.ts", "added_lines": 1, "deleted_lines": 0},
                    {"path": "pkg/foo_test.go", "added_lines": 1, "deleted_lines": 0},
                ],
            )
        ]

        with patch("black_box_unlock.git.history.fetch_git_history", return_value=history):
            result = run_analysis(Path("/fake/repo"), days=30, include_ci=False)

        roles = {file.path: file.path_role for file in result.files}
        assert roles == {"src/hooks/useThing.ts": "source", "pkg/foo_test.go": "test"}
        assert json.loads(export_to_json(result))["files"][0]["path_role"] in {"source", "test"}

    def test_path_role_honours_project_rules(self, tmp_path):
        (tmp_path / ".bbu.toml").write_text(
            '[[path_roles]]\npattern = "snapshots/**"\nrole = "generated"\n'
        )
        history = [
            make_commit(
                author_email="a@x.com",
                files=[{"path": "snapshots/a.py", "added_lines": 1, "deleted_lines": 0}],
            )
        ]

        with patch("black_box_unlock.git.history.fetch_git_history", return_value=history):
            result = run_analysis(tmp_path, days=30, include_ci=False)

        assert result.files[0].path_role == "generated"
